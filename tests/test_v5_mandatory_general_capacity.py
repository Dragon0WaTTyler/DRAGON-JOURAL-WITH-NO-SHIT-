"""Offline capacity tests. Captured minima are not uncaptured retrieval proof."""
from copy import deepcopy
import json
from pathlib import Path
import socket

import pytest

from dragon.deep_research_executor import (
    FixtureResearchAdapter, RoundActionBudget, continue_required_research_jobs,
    execute_scheduled_research_jobs, plan_research_actions, schedule_research_actions,
)
from dragon.hard_acquisition import HardAcquisition, CAPACITY_BLOCK, core
from dragon.providers import LocalCommandEditorialProvider
from test_v5_deep_research_executor import _job, CONFIG
from test_v5_research_finality import case, finality

LANES = ('ACCOUNTABILITY', 'SERVICE')
GENERAL_REASON = 'GENERAL_PREEMPTED_BY_MANDATORY_ACQUISITION'
FIXTURE = Path(__file__).parent / 'fixtures/mandatory-general-capacity-2026-10-06.json'


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('capacity regression attempted provider/network execution')
    monkeypatch.setattr(socket.socket, 'connect', forbidden)
    monkeypatch.setattr(socket.socket, 'connect_ex', forbidden)
    monkeypatch.setattr(LocalCommandEditorialProvider, '_invoke', forbidden)


def captured_audit():
    f = json.loads(FIXTURE.read_text(encoding='utf-8'))
    start = f['schedules'][1]['receipt']
    results = []
    for defer_general in (False, True):
        state = HardAcquisition(LANES, receipt=start)
        epoch1_actions = f['epochs'][1]['executed']
        if defer_general:
            # The known SERVICE alternate search moves to the eighth epoch-0
            # slot. Its captured result is RSS_NO_MATCHES, with no new route.
            state.completed(epoch1_actions[0])
            epoch1_actions = epoch1_actions[1:]
        timeline = [{'after':'epoch-1 selection', 'minimum':state.minimum(), 'remaining':8}]
        failures = {r['action_id']:r['reason'] for r in f['known_failures']}
        for index, a in enumerate(epoch1_actions, 1):
            state.completed(a)
            if a['action_id'] in failures:
                state.reject(a, failures[a['action_id']])
            if a['action_id'] == 'ACT-1098B8B5CD76':
                state.register(f['new_service_child'])
            timeline.append({'after':a['action_id'], 'minimum':state.minimum(),
                             'remaining':8-index, 'provenance':'derived from captured acquisition transitions'})
        remaining = 8-len(epoch1_actions)
        state.check_capacity(remaining)
        results.append({'general_deferred':defer_general, 'timeline':timeline,
                        'minimum':state.minimum(), 'remaining':remaining,
                        'selected':state.data['selected'], 'blocker':state.data['blocker']})
    return f, results


def test_captured_counterfactual_removes_recorded_refusal_but_not_missing_evidence():
    f, (actual, counterfactual) = captured_audit()
    assert actual['selected'] == f['epochs'][1]['receipt']['selected']
    assert (actual['minimum'], actual['remaining'], actual['blocker']) == (5,4,CAPACITY_BLOCK)
    assert (counterfactual['minimum'],counterfactual['remaining'],counterfactual['blocker']) == (5,5,None)
    assert [r['minimum'] for r in actual['timeline']] == [7,6,5,5,5]
    assert [r['minimum'] for r in counterfactual['timeline']] == [6,5,5,5]
    executed = [a for e in f['epochs'] for a in e['executed']]
    assert len(executed) == 12 and sum(core(a) for a in executed) == 8
    assert len([a for a in executed if a.get('target_editorial_function') in LANES]) == 11
    assert 11 + counterfactual['minimum'] == 16
    assert f['service_alternate_result'][0]['reason'] == 'RSS_NO_MATCHES'
    assert set(f['missing_capture_action_ids']).isdisjoint(a['action_id'] for a in executed)
    # Three concrete fetches + two unmaterialized role requests. No result or
    # positive/negative finality can be manufactured for those five requests.
    assert len(f['missing_capture_action_ids']) == 3


def protocol_jobs(path_count=8):
    jobs = []
    for lane, desk in zip(LANES, ('investigations','service')):
        native = _job(desk=desk)
        template = plan_research_actions(native, CONFIG)[0]
        native_actions = []
        for n in range(4):
            a = {**template, 'action_id':f'{lane}-core-{n}',
                 'target_editorial_function':lane, 'research_lane':lane,
                 'recovery_need_id':'CORE:'+lane, 'strategy_index':n,
                 'lead_origin':'NATIVE', 'provider_candidate_id':None}
            a.update(action_type='FETCH_CONFIGURED_SOURCE' if n==2 else 'SEARCH_DISCOVERY',
                     target='https://primary.example/navigation' if n==2 else None)
            native_actions.append(a)
        native['required_continuation_actions'] = native_actions
        exact = _job(desk=desk)
        exact['job_id'] += '-exact'
        template = plan_research_actions(exact, CONFIG)[0]
        exact['required_continuation_actions'] = [
            {**template, 'action_id':f'{lane}-artifact-{n}', 'action_type':'FETCH_URL',
             'target':f'https://primary.example/{lane}/{n}',
             'target_editorial_function':lane, 'research_lane':'HARD:'+lane,
             'lead_origin':'PROVIDER_EXACT', 'provider_candidate_id':lane+':active',
             'provider_source_role':'PRIMARY' if n==0 else 'INDEPENDENT', 'strategy_index':n}
            for n in range(path_count//2)]
        jobs.extend([native,exact])
    general = _job(desk='world')
    a = plan_research_actions(general, CONFIG)[0]
    a.update(action_id='GENERAL-root', action_type='FETCH_URL', target='https://context.example/context',
             research_lane='GENERAL_DISCOVERY',target_editorial_function=None,strategy_index=0)
    general['required_continuation_actions'] = [a]
    jobs.append(general)
    return jobs


def execute_epoch(jobs, receipt, remaining):
    schedule = schedule_research_actions(jobs, CONFIG, mandatory_lanes=LANES,
        acquisition_receipt=receipt,remaining_total_actions=remaining)
    budget = RoundActionBudget(8,schedule['actions'],acquisition=schedule['hard_acquisition'],
        mandatory_lanes=LANES,remaining_total_actions=remaining,general_action=schedule['general_opportunity'])
    grouped = {}
    for a in schedule['actions']:
        grouped.setdefault(a['job_id'],[]).append(a)
    # Explicit synthetic dead ends exercise acquisition execution, not evidence
    # acceptance. This fixture is separate from the sealed live response.
    adapter = FixtureResearchAdapter({t:[{'result_type':'DEAD_END','reason':'TEST_NO_EVIDENCE'}]
                                     for t in ('SEARCH_DISCOVERY','FETCH_CONFIGURED_SOURCE','FETCH_URL')})
    executions = execute_scheduled_research_jobs(jobs,adapter,CONFIG,grouped,budget)
    return schedule,budget,{'jobs':executions,'round_execution_budget':budget.report(),
                           'general_opportunity':schedule['general_opportunity']}


@pytest.mark.parametrize('path_count, expected_general',[(8,False),(6,True)])
def test_two_epochs_exact_sixteen_hard_actions_or_spare_general(path_count, expected_general):
    jobs = protocol_jobs(path_count)
    before = deepcopy(CONFIG)
    s0,b0,e0 = execute_epoch(jobs,{},16)
    assert len(b0.executed)==8 and 'GENERAL-root' not in b0.executed
    assert all(core(a) for a in s0['actions'])
    assert any(a['action_id']=='GENERAL-root' and a['deferred_reason']==GENERAL_REASON for a in s0['deferred_actions'])
    continuations = continue_required_research_jobs({'jobs':jobs},e0,CONFIG,LANES)
    general_job = next(j for j in continuations if j.get('general_opportunity_continuation'))
    assert general_job['required_continuation_actions'][0]['action_id']=='GENERAL-root'
    s1,b1,e1 = execute_epoch(continuations,b0.acquisition.report(),8)
    assert b1.acquisition.minimum()==0
    assert ('GENERAL-root' in b1.executed)==expected_general
    total = b0.executed+b1.executed
    assert len(total)==8+path_count+int(expected_general) <=16
    assert len(total)==len(set(total))
    if expected_general:
        assert b1.executed[-1]=='GENERAL-root'
    else:
        assert len(total)==16 and any(r['reason']==GENERAL_REASON for r in e1['round_execution_budget']['dynamic_actions_deferred'])
    assert CONFIG==before and CONFIG['executor']['maximum_actions_per_round']==8


def test_general_cannot_turn_a_fitting_mandatory_path_into_a_structural_block():
    jobs = protocol_jobs(8)
    pending = [a for j in jobs for a in j['required_continuation_actions'] if not core(a)]
    state = HardAcquisition(LANES,pending); state.promote()
    jobs = [j for j in jobs if not any(core(a) for a in j['required_continuation_actions'])]
    s,b,e = execute_epoch(jobs,state.report(),8)
    assert s['hard_acquisition']['blocker'] is None
    assert s['hard_acquisition']['minimum_remaining_required_actions']==8
    assert len(b.executed)==8 and 'GENERAL-root' not in b.executed


def test_foreseeable_unmaterialized_roles_protect_capacity_before_urls_exist():
    jobs = protocol_jobs(2)
    primary = deepcopy(jobs[1]['required_continuation_actions'][0])
    primary.pop('provider_source_role');primary.pop('provider_candidate_id')
    state = HardAcquisition(('ACCOUNTABILITY',),[primary]);state.promote()
    assert state.minimum()==3  # primary inspection + independent search + exact result
    general = jobs[-1]['required_continuation_actions'][0]
    budget = RoundActionBudget(8,[general],acquisition=state.report(),
        mandatory_lanes=('ACCOUNTABILITY',),remaining_total_actions=16)
    assert not budget.admit(general)
    assert budget.deferred[-1]['reason']==GENERAL_REASON
    assert budget.report()['hard_acquisition']['blocker'] is None


def test_intermediate_reporting_does_not_permanently_preempt_later_safe_general():
    jobs = protocol_jobs(4)
    hard = [a for j in jobs for a in j['required_continuation_actions'] if not core(a)]
    state = HardAcquisition(LANES,hard); state.promote()
    general = jobs[-1]['required_continuation_actions'][0]
    budget = RoundActionBudget(8,[general],acquisition=state.report(),mandatory_lanes=LANES,remaining_total_actions=8)
    assert budget.report()['dynamic_actions_deferred'][-1]['reason']==GENERAL_REASON
    assert budget.deferred==[]
    for a in budget.acquisition.actions():
        budget.acquisition.completed(a)
    assert budget.admit(general)
    assert budget.report()['dynamic_actions_deferred']==[]


def test_contingent_failure_promotes_only_its_lane_and_keeps_general_pending():
    f, _ = captured_audit()
    state = HardAcquisition(LANES,receipt=f['schedules'][1]['receipt'])
    old_service = state.data['selected']['SERVICE']
    pdf = f['epochs'][1]['executed'][1]
    state.completed(pdf); state.reject(pdf,'EXACT_CONTENT_OUTSIDE_CURRENT_EVENT_WINDOW')
    assert state.data['selected']['SERVICE']==old_service
    assert state.data['selected']['ACCOUNTABILITY']=='investigations:accountability_uk'
    general = f['epochs'][0]['executed'][-1]
    budget = RoundActionBudget(8,[general],acquisition=state.report(),mandatory_lanes=LANES,remaining_total_actions=8)
    assert not budget.admit(general)
    assert budget.acquisition.data['paths'][old_service]['state']=='SELECTED_FOR_QUALIFICATION'


def test_settled_acquisition_does_not_claim_a_validated_event_or_verified_absence():
    jobs = protocol_jobs(4)
    items = [a for j in jobs for a in j['required_continuation_actions'] if not core(a)]
    state = HardAcquisition(LANES,items); state.promote()
    for a in state.actions():
        state.completed(a)
    assert state.minimum()==0
    assert state.settled()
    assert not any(p['state'] in {'VALIDATED_EVENT','VERIFIED_NO_QUALIFYING_EVENT'} for p in state.data['paths'].values())


@pytest.mark.parametrize('incomplete',[False,True])
def test_general_preemption_cannot_change_hard_finality_or_editorial_handoff(case, incomplete):
    if incomplete:
        for job in case['epochs'][-1]['execution']['jobs']:
            job['actions']=[]
            job['observations']=[]
    before = finality(case)
    general = protocol_jobs()[-1]['required_continuation_actions'][0]
    case['epochs'][-1]['execution']['round_execution_budget']['dynamic_actions_deferred'] = [
        {'action':general,'reason':GENERAL_REASON}]
    after = finality(case)
    assert {n:v['state'] for n,v in after['lanes'].items()} == {n:v['state'] for n,v in before['lanes'].items()}
    assert after['editorial_handoff_eligible'] == before['editorial_handoff_eligible'] == (not incomplete)
    if incomplete:
        assert all(v['state'] not in {'VALIDATED_EVENT','VERIFIED_NO_QUALIFYING_EVENT'} for v in after['lanes'].values())
