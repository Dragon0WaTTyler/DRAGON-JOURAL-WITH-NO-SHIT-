from __future__ import annotations

from pathlib import Path
import sys

from dragon.providers import (
    LocalCommandEditorialProvider,
    ProviderError,
    SECTION_HEADINGS,
    UnconfiguredEditorialProvider,
    editorial_provider_from_config,
)


def _provider_script(path: Path) -> None:
    sections = repr(SECTION_HEADINGS)
    path.write_text(
        """import argparse, json, sys
SECTION_HEADINGS=__SECTIONS__
p=argparse.ArgumentParser(); p.add_argument('--operation', required=True); a=p.parse_args()
payload=json.load(sys.stdin)
if a.operation == 'healthcheck':
    value={'status':'PASS','unattended':True,'provider':'test-local'}
elif a.operation == 'research':
    sources=[{'id':'s1','url':'https://example.org/exact-page','publisher':'مصدر أولي اختباري','publication_date':'2099-01-02','accessed_at':'2099-01-02T07:00:00+01:00','source_type':'primary','claim_supported':'ادعاء اختباري'},{'id':'s2','url':'https://example.net/independent-page','publisher':'مصدر مستقل اختباري','publication_date':'2099-01-02','accessed_at':'2099-01-02T07:01:00+01:00','source_type':'independent','claim_supported':'مراجعة مستقلة'}]
    sections=[]
    for key,heading in SECTION_HEADINGS:
        candidates=[]
        for rank in (1,2):
            candidates.append({'id':f'{key}-c{rank}','rank':rank,'title':f'مرشح {rank}','discovery_source_ids':['s1'],'verification_source_ids':['s1','s2'],'primary_evidence_source_ids':['s1'],'independent_evidence_source_ids':['s2'],'facts':['حقيقة اختبارية'],'claims':[],'unknowns':[],'disputed_points':[]})
        sections.append({'section_id':key,'candidates':candidates,'selected_candidate_id':f'{key}-c1','selection_reason':'أفضل مرشح موثق في الاختبار'})
    value={'edition_date':payload['edition_date'],'sources':sources,'sections':sections}
elif a.operation == 'articles':
    words='كلمة عربية موثقة ' * 1400
    elements={key:'عنصر تحريري موثق' for key in ('lead','nut_graf','verified_facts','context','uncertainty','consequences','next_steps')}
    value=[]
    for index,(key,heading) in enumerate(SECTION_HEADINGS):
        if index == 0:
            value.append({'id':'a1','section_id':key,'section':heading,'status':'ACTIVE','headline':'عنوان عربي اختباري','standfirst':'مقدمة عربية واضحة','byline':'تحرير: DRAGON','body':[words],'source_ids':['s1','s2'],'research_candidate_id':f'{key}-c1','story_key':'story-a1','claims':[{'text':'ادعاء موثق','classification':'FACT','claim_type':'general','attribution':'مصدران اختباريان','source_ids':['s1','s2'],'material':True}],'editorial_elements':elements})
        else:
            value.append({'section_id':key,'section':heading,'status':'SKIPPED','skip_reason':'لا توجد مادة موثقة بما يكفي في هذا الاختبار'})
else:
    raise SystemExit(2)
json.dump(value, sys.stdout, ensure_ascii=False)
""".replace("__SECTIONS__", sections),
        encoding="utf-8",
    )


def test_local_command_provider_health_research_and_section_decisions(tmp_path: Path) -> None:
    script = tmp_path / "provider.py"
    _provider_script(script)
    provider = LocalCommandEditorialProvider((sys.executable, str(script)), timeout_seconds=30)
    assert provider.healthcheck()["unattended"] is True
    research = provider.research("2099-01-02")
    assert research["sources"][0]["url"] == "https://example.org/exact-page"
    assert len(research["sections"]) == 23
    decisions = provider.articles(research)
    assert len(decisions) == 23
    assert decisions[0]["status"] == "ACTIVE"
    assert all(item["status"] == "SKIPPED" for item in decisions[1:])


def test_provider_factory_cannot_claim_availability_before_proven_check(tmp_path: Path) -> None:
    script = tmp_path / "provider.py"
    _provider_script(script)
    config = {
        "providers": {
            "ai": {
                "type": "local-command",
                "integration_test_status": "NOT_RUN",
                "command": [sys.executable, str(script)],
            }
        }
    }
    assert isinstance(editorial_provider_from_config(config), UnconfiguredEditorialProvider)
    assert isinstance(
        editorial_provider_from_config(config, require_proven=False),
        LocalCommandEditorialProvider,
    )


def test_provider_rejects_homepage_as_exact_research_evidence(tmp_path: Path) -> None:
    script = tmp_path / "bad-provider.py"
    script.write_text(
        "import json,sys; p=json.load(sys.stdin); json.dump({'edition_date':p['edition_date'],'sources':[{'id':'s','url':'https://example.org/'}]},sys.stdout)",
        encoding="utf-8",
    )
    capture = tmp_path / "capture"
    provider = LocalCommandEditorialProvider(
        (sys.executable, str(script)), timeout_seconds=30, capture_directory=capture
    )
    try:
        provider.research("2099-01-02")
    except ProviderError as exc:
        assert exc.code == "RESEARCH_PACKET_INVALID"
        assert (capture / "research.raw.json").is_file()
    else:
        raise AssertionError("homepage was accepted as exact evidence")


def test_provider_retries_invalid_article_output_once_with_exact_feedback(tmp_path: Path) -> None:
    calls = []

    class InvalidArticleProvider(LocalCommandEditorialProvider):
        def _invoke(self, operation: str, payload: dict):
            assert operation == "articles"
            calls.append(payload)
            assert payload["quality_constraints"] == {
                "minimum_active_article_words": 350,
                "minimum_edition_words": 4000,
            }
            return [{"section_id": "front", "status": "ACTIVE"}]

    provider = InvalidArticleProvider(("unused",), capture_directory=tmp_path)
    research = {
        "sources": [{"id": "s1"}],
        "sections": [
            {"section_id": section_id, "selected_candidate_id": f"{section_id}-c1"}
            for section_id, _ in SECTION_HEADINGS
        ],
    }

    try:
        provider.articles(research)
    except ProviderError as exc:
        assert exc.code == "ARTICLE_SCHEMA_INVALID"
        assert len(calls) == 2
        repair = calls[1]["repair_context"]
        assert repair["attempt"] == repair["maximum_attempts"] == 2
        assert repair["validation_error"] == "active section front is incomplete"
        assert repair["previous_articles"] == [
            {"section_id": "front", "status": "ACTIVE"}
        ]
        assert (tmp_path / "articles.attempt-1.raw.json").is_file()
    else:
        raise AssertionError("invalid article output was accepted")


def test_research_section_error_identifies_missing_and_duplicate_ids() -> None:
    class InvalidResearchProvider(LocalCommandEditorialProvider):
        def _invoke(self, operation: str, payload: dict):
            sections = [
                {"section_id": section_id} for section_id, _ in SECTION_HEADINGS[:-1]
            ]
            sections.append({"section_id": SECTION_HEADINGS[0][0]})
            return {
                "edition_date": payload["edition_date"],
                "sources": [
                    {
                        "id": "s1",
                        "url": "https://example.org/article",
                        "publisher": "publisher",
                        "publication_date": "2099-01-02",
                        "accessed_at": "2099-01-02T07:00:00+01:00",
                        "source_type": "primary",
                        "claim_supported": "claim",
                    }
                ],
                "sections": sections,
            }

    try:
        InvalidResearchProvider(("unused",)).research("2099-01-02")
    except ProviderError as exc:
        assert exc.code == "RESEARCH_PACKET_INVALID"
        assert f"missing=['{SECTION_HEADINGS[-1][0]}']" in exc.detail
        assert f"duplicates=['{SECTION_HEADINGS[0][0]}']" in exc.detail
    else:
        raise AssertionError("invalid section inventory was accepted")
