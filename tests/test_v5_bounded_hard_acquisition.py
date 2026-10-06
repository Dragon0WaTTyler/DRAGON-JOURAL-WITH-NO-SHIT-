"""Offline admission proof; captured metadata never fabricates PDF evidence."""
from copy import deepcopy
import json
from pathlib import Path
import socket

import pytest

from dragon.hard_acquisition import HardAcquisition, CAPACITY_BLOCK, core, exact
from dragon.deep_research_executor import schedule_research_actions, RoundActionBudget, execute_research_round, FixtureResearchAdapter
from dragon.providers import LocalCommandEditorialProvider
from test_v5_research_finality import case, add_validated_event, finality

FIXTURE = Path(__file__).parent / 'fixtures/hard-acquisition-2026-10-06.json'
LANES = ('ACCOUNTABILITY', 'SERVICE')


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def forbidden(*a, **kw):
        pytest.fail('bounded acquisition regression attempted provider/network execution')
    monkeypatch.setattr(socket.socket, 'connect', forbidden)
    monkeypatch.setattr(socket.socket, 'connect_ex', forbidden)
    monkeypatch.setattr(LocalCommandEditorialProvider, '_invoke', forbidden)


def action(identity, *, lane='ACCOUNTABILITY', candidate='a', role='PRIMARY', pdf=False):
    return {'action_id':identity, 'job_id':'job-'+lane, 'action_type':'FETCH_URL',
        'target':f'https://{role.lower()}.example/{identity}' + ('.pdf' if pdf else ''),
        'target_editorial_function':lane, 'provider_candidate_id':lane+':'+candidate,
        'lead_origin':'PROVIDER_EXACT', 'provider_source_role':role,
        'strategy_index':0, 'priority_class':'P1_BREADTH'}


def pair(candidate='a', lane='ACCOUNTABILITY'):
    return [action(candidate+'-p',candidate=candidate,lane=lane),
            action(candidate+'-i',candidate=candidate,lane=lane,role='INDEPENDENT')]


def test_alternates_are_recorded_and_only_one_path_is_mandatory():
    items = pair('a') + pair('b') + pair('c')
    state = HardAcquisition(LANES, items)
    state.promote()
    assert [a['action_id'] for a in state.actions()] == ['a-p','a-i']
    assert state.minimum() == 2
    assert len(state.data['paths']) == 3
    assert all(state.data['paths']['ACCOUNTABILITY:'+c]['state'] == 'FALLBACK_IF_CURRENT_PATH_FAILS' for c in ('b','c'))
    assert not state.active(items[-1])


def test_explicit_failure_promotes_second_and_retains_reason():
    state = HardAcquisition(LANES, pair('a') + pair('b'))
    state.promote()
    chosen = state.actions()[0]
    state.completed(chosen)
    state.reject(chosen, 'EXACT_CONTENT_DOES_NOT_QUALIFY_FOR_TARGET_FUNCTION')
    assert state.data['selected']['ACCOUNTABILITY'] == 'ACCOUNTABILITY:b'
    assert state.data['paths']['ACCOUNTABILITY:a']['state'] == 'FAILED'
    assert state.data['paths']['ACCOUNTABILITY:a']['failure_reasons'] == [
        {'action_id':'a-p','reason':'EXACT_CONTENT_DOES_NOT_QUALIFY_FOR_TARGET_FUNCTION'}]
    assert {a['action_id'] for a in state.actions()} == {'b-p','b-i'}


def test_unresolved_qualification_does_not_promote_an_alternate():
    state = HardAcquisition(LANES, pair('a') + pair('b'))
    state.promote()
    state.completed(state.actions()[0])
    state.promote()
    assert state.data['selected']['ACCOUNTABILITY'] == 'ACCOUNTABILITY:a'


def test_exact_primary_child_outranks_generic_children_and_preserves_independent():
    state = HardAcquisition(LANES, pair('a') + pair('b'))
    state.promote()
    pdf = action('exact', pdf=True)
    pdf.update(acquisition_path_id='ACCOUNTABILITY:a', lead_followup=True)
    state.register(pdf)
    generic = {**action('generic'), 'acquisition_path_id':'ACCOUNTABILITY:a', 'lead_followup':True}
    state.register(generic)
    admitted = state.actions()
    assert admitted[0]['action_id'] == 'exact'
    assert any(a['provider_source_role'] == 'INDEPENDENT' for a in admitted)
    assert not any(a['action_id'].startswith('b-') for a in admitted)
    assert not state.active(generic)
    assert any('generic' in p['actions'] for p in state.data['paths'].values())


def test_minimum_includes_corroboration_fetch_after_discovery_query():
    p = action('primary',pdf=True)
    p.pop('provider_source_role')
    p.pop('provider_candidate_id')
    state = HardAcquisition(LANES,[p]); state.promote()
    assert state.minimum() == 3
    identity = state.data['selected']['ACCOUNTABILITY']
    query = {**p,'action_id':'corroboration-query','target':None,'action_type':'FIND_DISTINCT_EVENT',
             'event_lead_feedback':True,'acquisition_path_id':identity}
    state.register(query)
    assert state.minimum() == 3  # exact primary + independent query + exact fetch
    state.completed(query)
    assert state.minimum() == 2


@pytest.mark.parametrize('remaining,expected', [(4,None),(3,None),(2,CAPACITY_BLOCK),(0,CAPACITY_BLOCK)])
def test_capacity_invariant_is_explicit_before_execution(remaining, expected):
    p = action('native',pdf=True); p.pop('provider_candidate_id'); p.pop('provider_source_role')
    state = HardAcquisition(LANES,[p]); state.promote()
    assert state.check_capacity(remaining) == expected
    assert state.report()['minimum_remaining_required_actions'] == 3
    assert state.report()['remaining_execution_capacity'] == remaining


def test_lane_promotion_is_independent():
    state = HardAcquisition(LANES, pair('a')+pair('b')+pair('s','SERVICE'))
    state.promote()
    service = state.data['selected']['SERVICE']
    state.reject(state.actions()[0],'EXACT_CONTENT_OUTSIDE_CURRENT_EVENT_WINDOW')
    assert state.data['selected']['SERVICE'] == service
    assert {a['action_id'] for a in state.actions() if a['target_editorial_function']=='SERVICE'} == {'s-p','s-i'}


def captured():
    return json.loads(FIXTURE.read_text(encoding='utf-8'))


def captured_discovery_receipt():
    f = captured()
    state = HardAcquisition(LANES, f['epochs'][0]['planned'])
    for a in f['epochs'][0]['executed']:
        state.completed(a)
    for r in f['epochs'][0]['dynamic_deferred']:
        state.register(r['action'])
    return f,state


def test_sealed_october_six_before_all_slots_spent_and_exact_pdfs_uninspected():
    f = captured()
    executed = [a for e in f['epochs'] for a in e['executed']]
    assert len(executed) == 16
    assert sum(len(v['missing']) for v in f['before'].values()) == 17
    assert {k:len(v['required']) for k,v in f['before'].items()} == {'ACCOUNTABILITY':15,'SERVICE':17}
    assert sum(core(a) for a in executed) == 8
    pdfs = [r['action'] for e in f['epochs'] for r in e['dynamic_deferred'] if exact(r['action'])]
    assert len(pdfs)==2 and not {a['action_id'] for a in pdfs} & {a['action_id'] for a in executed}
    assert all(not o.get('content_hash') for e in f['epochs'] for o in e['observations'] if str(o.get('url')).endswith('.pdf'))
    assert f['source_sha']=='e705c4d81916dff324090c031b3b98cfd7d622eb'


def test_captured_after_selects_canonical_pdf_and_service_pair_within_unchanged_envelope(case):
    f,state = captured_discovery_receipt()
    state.promote()
    assert state.actions()[0]['action_id']=='ACT-0F29905AE800'
    assert state.data['selected']['SERVICE']=='service:service_01'
    assert state.check_capacity(8) is None
    assert state.minimum() == 6  # remaining core 1 + annual PDF 1 + independent 2 + SERVICE pair 2
    # The captured AMMPS child becomes required only after its selected parent.
    child = next(r['action'] for r in f['epochs'][1]['dynamic_deferred'] if exact(r['action']))
    child['acquisition_path_id']='service:service_01'
    state.register(child)
    assert state.minimum() == 7 and state.check_capacity(8) is None
    assert len(state.data['paths']) > 2
    assert not any(a['action_id']=='ACT-03C02631C24D' for a in state.actions())
    assert case['config']['executor']['maximum_actions_per_round']==8
    assert 8 + state.minimum() == 15 <= 16
    # These are acquisition identities only. No sealed observation qualified
    # either uninspected PDF, and this counterfactual must not claim closure.
    assert 'VALIDATED_EVENT' not in {p['state'] for p in state.data['paths'].values()}
    # The sealed independent SERVICE page was unresolved, so its recorded
    # additional-role query requires another exact inspection too. This stricter
    # active path cannot fit; refuse deterministically instead of claiming that
    # a nominally sufficient seven-action minimum proved evidence closure.
    feedback = next(r['action'] for r in f['epochs'][1]['dynamic_deferred']
                    if r['action']['action_id']=='ACT-F772D98D0DF4')
    feedback['acquisition_path_id']='service:service_01'
    state.register(feedback)
    assert state.minimum()==9
    assert state.check_capacity(8)==CAPACITY_BLOCK


def test_scheduler_admits_active_artifact_before_alternates_and_records_structural_block(case):
    f,state = captured_discovery_receipt()
    jobs = []
    for job_id in {a['job_id'] for a in f['epochs'][0]['planned']}:
        base = deepcopy(case['epochs'][0]['state']['jobs'][0])
        base.update(job_id=job_id, required_continuation_actions=[a for a in f['epochs'][0]['planned']
            if a['job_id']==job_id and a['action_id'] not in state.data['completed_action_ids']])
        jobs.append(base)
    # Candidate children belong to original jobs; the production continuation
    # merge retains those jobs rather than resetting any per-job allowance.
    for a in state.actions():
        assert any(j['job_id']==a['job_id'] for j in jobs)
    config_before = deepcopy(case['config'])
    schedule = schedule_research_actions(jobs,case['config'],mandatory_lanes=LANES,
        general_opportunity_executed=True,acquisition_receipt=state.report(),remaining_total_actions=8)
    selected = schedule['actions']
    assert any(a['action_id']=='ACT-0F29905AE800' for a in selected)
    assert not any(a['action_id']=='ACT-03C02631C24D' for a in selected)
    assert case['config']==config_before
    blocked = schedule_research_actions(jobs,case['config'],mandatory_lanes=LANES,
        general_opportunity_executed=True,acquisition_receipt=state.report(),remaining_total_actions=2)
    assert blocked['actions']==[] and blocked['hard_acquisition']['blocker']==CAPACITY_BLOCK


@pytest.mark.parametrize('same_captured_artifact',[False,True])
def test_qualified_bundle_closes_without_unselected_candidates_but_uninspected_selected_exact_blocks(case, same_captured_artifact):
    add_validated_event(case)
    executed = case['epochs'][0]['execution']['jobs'][0]['actions']
    selected = [{**a,'provider_candidate_id':'ACCOUNTABILITY:a','lead_origin':'PROVIDER_EXACT',
                 'provider_source_role':role} for a,role in zip(executed,('PRIMARY','INDEPENDENT'))]
    state = HardAcquisition(LANES,selected+pair('b')); state.promote()
    for a in state.actions():
        state.completed(a)
    # This fixture's accepted bundle is synthetic test evidence, deliberately
    # separate from the sealed October 6 metadata above.
    case['epochs'][-1]['execution']['round_execution_budget']['hard_acquisition']=state.report()
    result = finality(case)
    assert result['lanes']['ACCOUNTABILITY']['state']=='VALIDATED_EVENT'
    assert state.data['paths']['ACCOUNTABILITY:b']['state']=='FALLBACK_IF_CURRENT_PATH_FAILS'
    child=action('uninspected-exact',pdf=True)
    if same_captured_artifact:
        child['target']=selected[0]['target']
    child['acquisition_path_id']='ACCOUNTABILITY:a'
    state.register(child)
    case['epochs'][-1]['execution']['round_execution_budget']['hard_acquisition']=state.report()
    result=finality(case)['lanes']['ACCOUNTABILITY']
    if same_captured_artifact:
        assert result['state']=='VALIDATED_EVENT'
        assert result['reused_exact_acquisitions']['uninspected-exact'][0]['content_hash']
    else:
        assert result['state']!='VALIDATED_EVENT'
        assert 'uninspected-exact' in result['missing_action_ids']


def test_executor_preserves_optional_leads_without_promoting_every_search_result():
    from test_v5_deep_research_executor import _job, _result, CONFIG
    job = _job()
    from dragon.deep_research_executor import plan_research_actions
    a = plan_research_actions(job,CONFIG)[0]
    a.update(target_editorial_function='ACCOUNTABILITY',required_protocol=True,
             recovery_need_id='BREADTH:hard',action_type='SEARCH_DISCOVERY')
    state = HardAcquisition(('ACCOUNTABILITY',),[a])
    budget = RoundActionBudget(8,[a],acquisition=state.report(),mandatory_lanes=('ACCOUNTABILITY',),remaining_total_actions=16)
    adapter=FixtureResearchAdapter({'SEARCH_DISCOVERY':[_result('https://a.example/one','unknown'),_result('https://b.example/two','unknown')]})
    adapter.follow_discovery_leads=True
    result=execute_research_round(job,adapter,CONFIG,actions=[a],round_budget=budget)
    assert len(result['actions'])==1
    assert len(budget.acquisition.data['paths'])>=2
    assert not budget.acquisition.data['selected']
    assert all(r['reason']=='FALLBACK_IF_CURRENT_PATH_FAILS' for r in result['unexecuted_actions'])


def test_capacity_block_never_grants_absence_or_editorial_handoff(case):
    state = HardAcquisition(LANES,pair());state.promote();state.check_capacity(0)
    case['epochs'][-1]['execution']['round_execution_budget']['hard_acquisition']=state.report()
    record=finality(case)
    assert record['lanes']['ACCOUNTABILITY']['reason']==CAPACITY_BLOCK
    assert record['research_finality']=='BLOCKED'
    assert record['editorial_handoff_eligible'] is False


def test_failed_inspection_dispatches_promoted_job_and_required_independent_inside_same_cap():
    from test_v5_deep_research_executor import _job, _result, CONFIG
    from dragon.deep_research_executor import plan_research_actions, execute_scheduled_research_jobs
    first=_job(desk='investigations')
    second=deepcopy(first);second['job_id']='fallback-job'
    template=plan_research_actions(first,CONFIG)[0]
    template['research_date']='2099-01-02'
    template['event_context']['research_date']='2099-01-02'
    first_actions=[{**template,**a,'job_id':first['job_id'],'required_protocol':True} for a in pair('a')]
    second_actions=[{**template,**a,'job_id':second['job_id'],'required_protocol':True} for a in pair('b')]
    registry=HardAcquisition(('ACCOUNTABILITY',),first_actions+second_actions);registry.promote()
    budget=RoundActionBudget(8,first_actions,acquisition=registry.report(),mandatory_lanes=('ACCOUNTABILITY',),remaining_total_actions=8)
    responses={a['action_id']:[_result(a['target'],'unknown',title='A sports event',text='Sports results from a tournament.',fetch_status='FETCHED')]
               for a in first_actions}
    responses.update({a['action_id']:[_result(a['target'],'unknown',title='Public regulator publishes audit findings',
        text='Public authority publishes an audit report documenting oversight findings. '*8,fetch_status='FETCHED')]
        for a in second_actions})
    adapter=FixtureResearchAdapter(responses)
    records=execute_scheduled_research_jobs([first,second],adapter,CONFIG,{first['job_id']:first_actions},budget)
    ids=[a['action_id'] for r in records for a in r['actions']]
    assert ids[:3]==['a-p','b-p','b-i']
    assert 'a-i' not in ids
    assert sum(a['action_type']=='FIND_DISTINCT_EVENT' for r in records for a in r['actions'])==1
    assert budget.executed==ids and len(ids)<=8
    assert registry.data['paths']['ACCOUNTABILITY:a']['failure_reasons']==[]  # input is immutable
    assert budget.acquisition.data['paths']['ACCOUNTABILITY:a']['failure_reasons'][0]['reason']=='EXACT_CONTENT_DOES_NOT_QUALIFY_FOR_TARGET_FUNCTION'
    assert records[1]['budget_consumed']['fetches']==2
    assert all(r['job']['round']==1 for r in records)


def test_selected_late_role_search_inspects_one_exact_result_without_third_epoch():
    from test_v5_deep_research_executor import _job, _result, CONFIG
    from dragon.deep_research_executor import plan_research_actions
    job=_job(desk='investigations')
    template=plan_research_actions(job,CONFIG)[0]
    template['event_context']['research_date']='2099-01-02'
    query={**template,**action('role-query',role='INDEPENDENT'),'job_id':job['job_id'],
        'action_type':'FIND_DISTINCT_EVENT','target':None,'query':'public audit findings Morocco',
        'research_date':'2099-01-02','event_lead_feedback':True,'required_protocol':True,
        'provenance_requirements':{'required_role':'INDEPENDENT'}}
    primary=action('already-inspected-primary')
    primary['job_id']=job['job_id']
    state=HardAcquisition(('ACCOUNTABILITY',),[primary,query]);state.completed(primary);state.promote()
    budget=RoundActionBudget(8,[query],acquisition=state.report(),mandatory_lanes=('ACCOUNTABILITY',),remaining_total_actions=8)
    adapter=FixtureResearchAdapter({'role-query':[
        {'result_type':'LEAD','url':'https://medias24.com/one-audit','title':'Morocco public audit findings','source_class':'unknown'},
        {'result_type':'LEAD','url':'https://hespress.com/another-audit','title':'Morocco public audit findings','source_class':'unknown'}],
        'FETCH_URL':[_result('https://medias24.com/one-audit','unknown',title='Public regulator publishes audit findings',
            text='Public authority publishes an audit report documenting oversight findings. '*8,fetch_status='FETCHED')]})
    result=execute_research_round(job,adapter,CONFIG,actions=[query],round_budget=budget)
    assert result['actions'][0]['action_id']=='role-query'
    children=[a for a in result['actions'] if a['action_type']=='FETCH_URL']
    assert len(children)==1
    assert children[0]['provenance_requirements']['required_role']=='INDEPENDENT'
    assert children[0]['required_protocol'] is True
    assert len(result['actions'])==2 and result['job']['round']==1
    assert len(budget.acquisition.data['paths'])>1


@pytest.mark.parametrize('eligible',[False,True])
def test_existing_primary_only_policy_releases_optional_corroboration_only_after_qualification(eligible):
    from dragon.evidence_policy import candidate_evidence_policy
    state=HardAcquisition(('SERVICE',),pair('a','SERVICE'));state.promote()
    primary=state.actions()[0];state.completed(primary)
    policy=candidate_evidence_policy({'title':'Ministry announces registration procedure',
        'facts':['The ministry opens registration and states the current deadline.'],
        'primary_evidence_source_ids':['p']},{'p':{'source_type':'primary'}},section_id='service')
    observation={'observation_id':'qualified-fixture','content_hash':'fixture-hash','exact_artifact_reached':True,
        'post_fetch_qualification':{'state':'ELIGIBLE_OBSERVATION' if eligible else 'QUALIFICATION_BLOCKED'},
        'source_role_resolution':{'evidence_role':'PRIMARY'},'temporal_relevance':{'active_on_edition_date':True}}
    assert policy['required_roles']==['PRIMARY']
    state.qualified_primary_policy(primary,policy,observation)
    assert [a['provider_source_role'] for a in state.actions()]==([] if eligible else ['INDEPENDENT'])
    assert state.minimum()==(0 if eligible else 1)


@pytest.mark.parametrize('mandatory',[LANES,('ACCOUNTABILITY',),('SERVICE',),()])
def test_staging_is_scoped_to_each_mandatory_lane_and_preserves_optional_exact_preference(case, mandatory):
    from test_v5_hard_capacity import recorded
    jobs=recorded()['epochs'][0]['jobs']
    schedule=schedule_research_actions(jobs,case['config'],mandatory_lanes=mandatory,
        acquisition_receipt={},remaining_total_actions=16)
    for name in LANES:
        admitted=[a for a in schedule['actions'] if a.get('target_editorial_function')==name]
        if name in mandatory:
            assert core(admitted[0]) and all(a.get('required_protocol') for a in admitted)
        else:
            assert [a.get('provider_source_role') for a in admitted[:2]]==['PRIMARY','INDEPENDENT']
            assert all(not a.get('required_protocol') for a in admitted)
    assert len(schedule['actions'])<=8
    assert case['config']['executor']['maximum_actions_per_round']==8
    assert not schedule['budget_allocation']['budget_increased']


def test_optional_service_keeps_ordinary_child_followup_under_an_accountability_receipt():
    from test_v5_deep_research_executor import _job, _result, CONFIG
    from dragon.deep_research_executor import plan_research_actions
    job=_job(desk='service')
    a=plan_research_actions(job,CONFIG)[0]
    a.update(action_type='SEARCH_DISCOVERY',target_editorial_function='SERVICE')
    state=HardAcquisition(('ACCOUNTABILITY',))
    budget=RoundActionBudget(8,[a],acquisition=state.report(),mandatory_lanes=('ACCOUNTABILITY',),remaining_total_actions=16)
    adapter=FixtureResearchAdapter({'SEARCH_DISCOVERY':[{'result_type':'LEAD','url':'https://medias24.com/optional-service',
        'title':'Public service registration opens','source_class':'unknown'}],
        'FETCH_URL':[_result('https://medias24.com/optional-service','unknown',fetch_status='FETCHED',
            text='Public service registration opens with a current deadline. '*8)]})
    adapter.follow_discovery_leads=True
    result=execute_research_round(job,adapter,CONFIG,actions=[a],round_budget=budget)
    assert any(x['action_type']=='FETCH_URL' and x.get('lead_followup') for x in result['actions'])
    assert not budget.acquisition.data['paths']


@pytest.mark.parametrize('mandatory', ['ACCOUNTABILITY', 'SERVICE'])
@pytest.mark.parametrize('real_general', [False, True])
def test_optional_hard_lane_is_not_general_and_is_dropped_for_exact_mandatory_capacity(case, mandatory, real_general):
    optional = next(name for name in LANES if name != mandatory)
    items = pair('mandatory', mandatory) + pair('optional', optional)
    if real_general:
        items.append({**action('real-general'), 'job_id':'general-job', 'target_editorial_function':None,
                      'research_lane':'GENERAL_DISCOVERY', 'provider_candidate_id':None})
    jobs = []
    for job_id in dict.fromkeys(a['job_id'] for a in items):
        job = deepcopy(case['epochs'][0]['state']['jobs'][0])
        job.update(job_id=job_id,required_continuation_actions=[a for a in items if a['job_id']==job_id])
        jobs.append(job)
    state = HardAcquisition((mandatory,),items); state.promote()
    config_before = deepcopy(case['config'])
    remaining = 2 + int(real_general)
    schedule = schedule_research_actions(jobs,case['config'],mandatory_lanes=(mandatory,),
        acquisition_receipt=state.report(),remaining_total_actions=remaining)
    assert schedule['hard_acquisition']['blocker'] is None
    assert schedule['hard_acquisition']['minimum_remaining_required_actions']==remaining
    assert {a['action_id'] for a in schedule['actions'] if a.get('target_editorial_function')==mandatory}=={'mandatory-p','mandatory-i'}
    assert not any(a.get('target_editorial_function')==optional for a in schedule['actions'])
    assert [a['action_id'] for a in schedule['actions'] if a.get('target_editorial_function') not in LANES]==(['real-general'] if real_general else [])
    assert all(not a['required_protocol'] for a in schedule['deferred_actions'] if a.get('target_editorial_function')==optional)
    assert schedule['budget_allocation']['hard_breadth_reserved_slots']==int(real_general)
    assert case['config']==config_before and len(schedule['actions'])==remaining


def test_neither_of_two_mandatory_lanes_consumes_a_general_reservation(case):
    items = pair('a') + pair('s','SERVICE')
    state = HardAcquisition(LANES,items); state.promote()
    jobs = []
    for job_id in dict.fromkeys(a['job_id'] for a in items):
        job = deepcopy(case['epochs'][0]['state']['jobs'][0])
        job.update(job_id=job_id,required_continuation_actions=[a for a in items if a['job_id']==job_id])
        jobs.append(job)
    schedule = schedule_research_actions(jobs,case['config'],mandatory_lanes=LANES,
        acquisition_receipt=state.report(),remaining_total_actions=4)
    assert schedule['hard_acquisition']['blocker'] is None
    assert schedule['hard_acquisition']['minimum_remaining_required_actions']==4
    assert schedule['budget_allocation']['hard_breadth_reserved_slots']==0
    assert {a['action_id'] for a in schedule['actions']}=={'a-p','a-i','s-p','s-i'}


@pytest.mark.parametrize('mandatory',['ACCOUNTABILITY','SERVICE'])
def test_optional_lane_cannot_keep_slots_when_all_eight_are_needed_by_the_active_path(case, mandatory):
    optional = next(name for name in LANES if name != mandatory)
    native = []
    for n in range(4):
        a = action('core-'+str(n),lane=mandatory)
        a.update(job_id='native-job',recovery_need_id='BREADTH:active',lead_origin='NATIVE',
                 provider_candidate_id=None,strategy_index=n,strategy_count=4)
        if n<3:
            a.update(action_type='SEARCH_DISCOVERY',target=None,query='native query '+str(n))
        else:
            a['action_type']='FETCH_CONFIGURED_SOURCE'
        native.append(a)
    selected = pair('selected',mandatory) + [
        action('selected-exact',lane=mandatory,candidate='selected',pdf=True),
        action('selected-independent',lane=mandatory,candidate='selected',role='INDEPENDENT')]
    items = native + selected + pair('optional',optional)
    state = HardAcquisition((mandatory,),items); state.promote()
    jobs = []
    for job_id in dict.fromkeys(a['job_id'] for a in items):
        job = deepcopy(case['epochs'][0]['state']['jobs'][0])
        job.update(job_id=job_id,required_continuation_actions=[a for a in items if a['job_id']==job_id])
        jobs.append(job)
    schedule = schedule_research_actions(jobs,case['config'],mandatory_lanes=(mandatory,),
        acquisition_receipt=state.report(),remaining_total_actions=8)
    assert schedule['hard_acquisition']['minimum_remaining_required_actions']==8
    assert schedule['hard_acquisition']['blocker'] is None
    assert {a['action_id'] for a in schedule['actions']}=={a['action_id'] for a in native+selected}
    assert all(not a['required_protocol'] for a in schedule['deferred_actions'])


def returning_job_fixture(round_number=0):
    from test_v5_deep_research_executor import _job, _result, CONFIG
    from dragon.deep_research_executor import plan_research_actions
    first = _job(desk='investigations'); first['round']=round_number
    first['executor_state']={'search_actions':0,'fetches':1,'lead_followups':0,
        'seen_urls':[],'seen_origins':[],'route_memory':[],'actions_executed':1}
    second = deepcopy(first); second['job_id']='middle-job'
    second['executor_state']['fetches']=0; second['executor_state']['actions_executed']=0
    template = plan_research_actions(first,CONFIG)[0]
    template['research_date']='2099-01-02'; template['event_context']['research_date']='2099-01-02'
    items = [{**template,**a,'job_id':job['job_id'],'required_protocol':True}
             for candidate,job in [('a',first),('b',second),('c',first)] for a in pair(candidate)]
    registry = HardAcquisition(('ACCOUNTABILITY',),items); registry.promote()
    responses = {a['action_id']:[_result(a['target'],'unknown',fetch_status='FETCHED',
        title='A sports event' if a['action_id'][0] in 'ab' else 'Public regulator publishes audit findings',
        text='Sports tournament results. '*8 if a['action_id'][0] in 'ab'
            else 'Public authority publishes an audit report documenting oversight findings. '*8)] for a in items}
    return [first,second],items,registry,responses,CONFIG


@pytest.mark.parametrize('round_number',[0,1])
def test_action_level_redispatch_returns_to_a_without_repeating_actions_or_advancing_another_round(round_number):
    from dragon.deep_research_executor import execute_scheduled_research_jobs
    ledgers = []
    for replay in range(2):
        jobs,items,state,responses,config=returning_job_fixture(round_number)
        initial = [a for a in items if a['provider_candidate_id']=='ACCOUNTABILITY:a']
        budget = RoundActionBudget(8,initial,acquisition=state.report(),mandatory_lanes=('ACCOUNTABILITY',),remaining_total_actions=8)
        adapter = FixtureResearchAdapter(responses)
        records = execute_scheduled_research_jobs(jobs,adapter,config,{jobs[0]['job_id']:initial},budget)
        assert adapter.executed_actions[:4]==['a-p','b-p','c-p','c-i']
        assert budget.executed==adapter.executed_actions
        assert len(budget.executed)==len(set(budget.executed))<=8
        assert 'a-i' not in budget.executed and 'b-i' not in budget.executed
        first = next(r for r in records if r['job']['job_id']==jobs[0]['job_id'])
        assert [a['action_id'] for a in first['actions'] if a['action_type']=='FETCH_URL']==['a-p','c-p','c-i']
        assert first['budget_consumed']['fetches']==4  # original 1 + three new fetches
        assert first['job']['executor_state']['actions_executed']==1+len(first['actions'])
        assert all(r['job']['round']==round_number+1<=2 for r in records)
        assert any(o.get('provenance',{}).get('action_id')=='a-p' for o in first['job']['observations'])
        assert any(o.get('provenance',{}).get('action_id')=='c-p' for o in first['job']['observations'])
        assert budget.acquisition.data['selected']['ACCOUNTABILITY']=='ACCOUNTABILITY:c'
        assert all(budget.acquisition.data['paths']['ACCOUNTABILITY:'+c]['failure_reasons'] for c in 'ab')
        assert jobs[0]['executor_state']['fetches']==1 and jobs[0]['round']==round_number
        ledgers.append(budget.executed)
    assert ledgers[0]==ledgers[1]


def test_exhausted_shared_round_does_not_redispatch_a_new_action():
    from dragon.deep_research_executor import execute_scheduled_research_jobs
    jobs,items,state,responses,config=returning_job_fixture()
    initial = [a for a in items if a['provider_candidate_id']=='ACCOUNTABILITY:a']
    budget = RoundActionBudget(8,initial,acquisition=state.report(),mandatory_lanes=('ACCOUNTABILITY',),remaining_total_actions=16)
    budget.executed=[f'earlier-optional-{n}' for n in range(6)]
    adapter = FixtureResearchAdapter(responses)
    execute_scheduled_research_jobs(jobs,adapter,config,{jobs[0]['job_id']:initial},budget)
    assert adapter.executed_actions==['a-p','b-p']
    assert budget.executed[6:]==['a-p','b-p'] and len(budget.executed)==8
    assert budget.acquisition.data['selected']['ACCOUNTABILITY']=='ACCOUNTABILITY:c'
    assert {a['action_id'] for a in budget.acquisition.actions()}=={'c-p','c-i'}
