from __future__ import annotations

import copy
import json
from pathlib import Path
import sys

import pytest

from dragon.config import load_local_config
from dragon.providers import (
    LocalCommandEditorialProvider,
    ProviderError,
    SECTION_HEADINGS,
    SyntheticEditorialProvider,
    UnconfiguredEditorialProvider,
    editorial_provider_from_config,
    configured_byline,
)


ROOT = Path(__file__).resolve().parents[1]


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
    sources=[{'id':'s1','url':'https://example.org/exact-page','publisher':'مصدر أولي اختباري','publication_date':'2099-01-02','accessed_at':'2099-01-02T07:00:00+01:00','source_type':'primary','claim_supported':'ادعاء اختباري','doi':None,'publication_status':'report','full_text_status':'FULL_TEXT_VERIFIED','methods_read':True,'limitations_read':True,'science_metadata':None},{'id':'s2','url':'https://example.net/independent-page','publisher':'مصدر مستقل اختباري','publication_date':'2099-01-02','accessed_at':'2099-01-02T07:01:00+01:00','source_type':'independent','claim_supported':'مراجعة مستقلة','doi':None,'publication_status':'news','full_text_status':'NOT_APPLICABLE','methods_read':False,'limitations_read':False,'science_metadata':None}]
    sections=[]
    for key,heading in SECTION_HEADINGS:
        candidates=[]
        for rank in (1,2):
            candidates.append({'id':f'{key}-c{rank}','rank':rank,'title':f'مرشح {rank}','discovery_source_ids':['s1'],'verification_source_ids':['s1','s2'],'primary_evidence_source_ids':['s1'],'independent_evidence_source_ids':['s2'],'facts':['حقيقة اختبارية'],'claims':[],'unknowns':[],'disputed_points':[]})
        sections.append({'section_id':key,'status':'ACTIVE','candidates':candidates,'selected_candidate_id':f'{key}-c1','selection_reason':'أفضل مرشح موثق في الاختبار','no_news_reason':None,'fallback_action':None})
    value={'edition_date':payload['edition_date'],'sources':sources,'sections':sections}
elif a.operation == 'articles':
    words='كلمة عربية موثقة ' * 1400
    elements={key:'عنصر تحريري موثق' for key in ('lead','nut_graf','verified_facts','context','uncertainty','consequences','next_steps')}
    value=[]
    for index,(key,heading) in enumerate(SECTION_HEADINGS):
        if index == 0:
            value.append({'id':'a1','section_id':key,'section':heading,'status':'ACTIVE','headline':'عنوان عربي اختباري','standfirst':'مقدمة عربية واضحة','byline':'تحرير: DRAGON','body':[words],'source_ids':['s1','s2'],'research_candidate_id':f'{key}-c1','story_key':'story-a1','story_type':'NEWS','claims':[{'text':'ادعاء موثق','classification':'FACT','claim_type':'general','attribution':'مصدران اختباريان','source_ids':['s1','s2'],'material':True}],'editorial_elements':elements})
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
    provider = LocalCommandEditorialProvider(
        (sys.executable, str(script)), timeout_seconds=30,
        minimum_active_sections=1, minimum_edition_words=350,
    )
    assert provider.healthcheck()["unattended"] is True
    research = provider.research("2099-01-02")
    assert research["sources"][0]["url"] == "https://example.org/exact-page"
    assert len(research["sections"]) == 23
    for section in research["sections"][1:]:
        section.update({
            "status": "NO_NEWS", "candidates": [], "selected_candidate_id": None,
            "selection_reason": None,
            "no_news_reason": "لا توجد مادة موثقة كافية للنشر في هذا القسم التجريبي",
            "fallback_action": "SKIP",
        })
    decisions = provider.articles(research)
    assert len(decisions) == 23
    assert decisions[0]["status"] == "ACTIVE"
    assert all(item["status"] == "SKIPPED" for item in decisions[1:])


def test_provider_execution_failure_keeps_terminal_diagnostic(tmp_path: Path) -> None:
    script = tmp_path / "failing-provider.py"
    script.write_text(
        "import sys; sys.stderr.write('prompt ' * 800 + 'AUTHORIZATION_REQUIRED'); raise SystemExit(1)",
        encoding="utf-8",
    )
    provider = LocalCommandEditorialProvider((sys.executable, str(script)), timeout_seconds=30)

    with pytest.raises(ProviderError) as caught:
        provider.research("2099-01-02")

    assert caught.value.code == "AI_PROVIDER_EXECUTION_FAILED"
    assert "AUTHORIZATION_REQUIRED" in caught.value.detail
    assert len(caught.value.detail) == 2000
    assert caught.value.detail.endswith("AUTHORIZATION_REQUIRED")


@pytest.mark.parametrize(
    ("needle", "replacement"),
    [
        ("'ادعاء اختباري'", repr("مادة منسوخة " * 80)),
        ("['حقيقة اختبارية']", repr(["مادة منسوخة " * 80])),
    ],
)
def test_provider_rejects_source_prose_disguised_as_research_metadata(
    tmp_path: Path, needle: str, replacement: str
) -> None:
    script = tmp_path / "provider.py"
    _provider_script(script)
    original = script.read_text(encoding="utf-8")
    script.write_text(
        original.replace(needle, replacement),
        encoding="utf-8",
    )
    provider = LocalCommandEditorialProvider(
        (sys.executable, str(script)), timeout_seconds=30
    )

    with pytest.raises(ProviderError) as caught:
        provider.research("2099-01-02")

    assert caught.value.code == "RESEARCH_PACKET_INVALID"


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


def test_provider_enforces_configured_editorial_identity() -> None:
    config = {
        "publication": {
            "byline_template": "تحرير: {pen_name}",
            "pen_name": "اسم القلم",
        },
        "providers": {
            "ai": {
                "type": "local-command",
                "integration_test_status": "NOT_RUN",
                "command": [sys.executable, "unused.py"],
            }
        },
    }
    provider = editorial_provider_from_config(config, require_proven=False)
    assert isinstance(provider, LocalCommandEditorialProvider)
    assert provider.expected_byline == "تحرير: اسم القلم"

    articles = SyntheticEditorialProvider().articles(
        SyntheticEditorialProvider().research("2099-01-02")
    )
    research = SyntheticEditorialProvider().research("2099-01-02")
    try:
        provider._validate_articles(articles, research)
    except ProviderError as exc:
        assert exc.code == "ARTICLE_SCHEMA_INVALID"
        assert "configured editorial identity" in exc.detail
    else:
        raise AssertionError("hard-coded byline bypassed configured identity")


def test_byline_template_rejects_missing_or_unsafe_placeholder() -> None:
    for template in ("تحرير ثابت", "{pen_name.__class__}", "{pen_name!r}", "{other}"):
        try:
            configured_byline({
                "publication": {"byline_template": template, "pen_name": "اسم القلم"}
            })
        except ValueError as exc:
            assert str(exc) == "PUBLICATION_BYLINE_CONFIG_INVALID"
        else:
            raise AssertionError(f"invalid byline template accepted: {template}")


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


def test_provider_rejects_bad_source_dates_before_chronology() -> None:
    class BadDateProvider(LocalCommandEditorialProvider):
        def _invoke(self, operation: str, payload: dict) -> dict:
            value = SyntheticEditorialProvider().research(payload["edition_date"])
            value["sources"][0]["publication_date"] = "sometime recently"
            return value

    try:
        BadDateProvider(("unused",)).research("2099-01-02")
    except ProviderError as exc:
        assert exc.code == "RESEARCH_PACKET_INVALID"
    else:
        raise AssertionError("invalid publication date entered source chronology")


def test_provider_rejects_partial_source_date_and_stamps_its_own_retrieval_time() -> None:
    class PartialDateProvider(LocalCommandEditorialProvider):
        def _invoke(self, operation: str, payload: dict) -> dict:
            value = SyntheticEditorialProvider().research(payload["edition_date"])
            value["sources"][0]["publication_date"] = "2099-01"
            value["sources"][0]["accessed_at"] = "2099-01-02"
            return value

    try:
        PartialDateProvider(("unused",)).research("2099-01-02")
    except ProviderError as exc:
        assert exc.code == "RESEARCH_PACKET_INVALID"
    else:
        raise AssertionError("partial publication date entered source chronology")

    class RetrievalStampProvider(LocalCommandEditorialProvider):
        def _invoke(self, operation: str, payload: dict) -> dict:
            value = SyntheticEditorialProvider().research(payload["edition_date"])
            value["sources"][0]["accessed_at"] = "date-only-model-value"
            return value

    research = RetrievalStampProvider(("unused",)).research("2099-01-02")
    assert "T" in research["sources"][0]["accessed_at"]
    assert research["sources"][0]["accessed_at"].endswith("+00:00")


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
    research = SyntheticEditorialProvider().research("2099-01-02")

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
        assert "zero-active or aggregate-word failure" in repair["instruction"]
        assert (tmp_path / "articles.attempt-1.raw.json").is_file()
    else:
        raise AssertionError("invalid article output was accepted")


def test_all_no_news_research_blocks_article_provider_before_live_invocation() -> None:
    research = json.loads(
        (ROOT / "tests" / "fixtures" / "live_provider_all_no_news.json").read_text(
            encoding="utf-8"
        )
    )

    class RecordingProvider(LocalCommandEditorialProvider):
        def _invoke(self, operation: str, payload: dict):
            raise AssertionError(f"article provider must not run for insufficient research: {operation}")

    with pytest.raises(ProviderError) as caught:
        RecordingProvider(("unused",)).articles(research)

    assert caught.value.code == "RESEARCH_INSUFFICIENT"
    assert "1 sources, 23 section decisions" in caught.value.detail


def test_validated_all_no_news_research_never_reaches_article_provider() -> None:
    raw_research = SyntheticEditorialProvider().research("2099-01-02")
    for section in raw_research["sections"]:
        section.update(
            {
                "status": "NO_NEWS",
                "candidates": [],
                "selected_candidate_id": None,
                "selection_reason": None,
                "no_news_reason": "لا توجد أدلة كافية لنشر مادة في هذا القسم اليوم",
                "fallback_action": "RADAR",
            }
        )
    calls: list[str] = []

    class RecordingProvider(LocalCommandEditorialProvider):
        def _invoke(self, operation: str, payload: dict):
            calls.append(operation)
            if operation == "research":
                return raw_research
            raise AssertionError(f"article provider must not run: {operation}")

    provider = RecordingProvider(("unused",))
    research = provider.research("2099-01-02")
    with pytest.raises(ProviderError, match="0 selected section"):
        provider.articles(research)

    assert calls == ["research"]


def _configured_readiness_provider(provider_type=LocalCommandEditorialProvider):
    configured = editorial_provider_from_config(load_local_config(ROOT), require_proven=False)
    assert isinstance(configured, LocalCommandEditorialProvider)
    return provider_type(
        ("unused",),
        minimum_active_sections=configured.minimum_active_sections,
        coverage_requirements=configured.coverage_requirements,
    )


def test_inherited_edition_architecture_drives_provider_readiness() -> None:
    provider = _configured_readiness_provider()

    assert provider.minimum_active_sections == 10
    assert provider.coverage_requirements == (
        ("morocco_breadth", (
            "siyasa_dawla", "iqtisad_flous", "mojtama3", "ta3lim", "se77a",
            "3adl_7o9o9", "bi2a_manakh", "bniya_transport",
        ), 3),
        ("world_breadth", ("filastin_middle_east", "africa_sahel", "world"), 2),
        ("reader_life", ("ta3lim", "se77a", "technology", "science", "sport", "culture", "service"), 2),
        ("accountability_and_service", ("investigations", "opinion", "service"), 2),
    )


def test_one_selected_lead_blocks_before_article_provider_invocation() -> None:
    research = json.loads(
        (ROOT / "tests" / "fixtures" / "live_provider_one_lead_insufficient.json").read_text(
            encoding="utf-8"
        )
    )
    calls: list[str] = []

    class RecordingProvider(LocalCommandEditorialProvider):
        def _invoke(self, operation: str, payload: dict):
            calls.append(operation)
            raise AssertionError("insufficient research must not reach the article provider")

    provider = _configured_readiness_provider(RecordingProvider)
    with pytest.raises(ProviderError) as caught:
        provider.articles(research)

    assert caught.value.code == "RESEARCH_INSUFFICIENT"
    assert "1 selected section(s)" in caught.value.detail
    assert "at least 10 active sections" in caught.value.detail
    assert calls == []


def test_validated_one_lead_research_blocks_before_article_provider_invocation() -> None:
    raw_research = SyntheticEditorialProvider().research("2099-01-02")
    for section in raw_research["sections"]:
        if section["section_id"] == "service":
            continue
        section.update(
            {
                "status": "NO_NEWS",
                "candidates": [],
                "selected_candidate_id": None,
                "selection_reason": None,
                "no_news_reason": "لا توجد أدلة كافية لنشر مادة في هذا القسم اليوم",
                "fallback_action": "RADAR",
            }
        )
    calls: list[str] = []

    class RecordingProvider(LocalCommandEditorialProvider):
        def _invoke(self, operation: str, payload: dict):
            calls.append(operation)
            if operation == "research":
                return raw_research
            raise AssertionError("one selected lead must not reach article generation")

    provider = _configured_readiness_provider(RecordingProvider)
    research = provider.research("2099-01-02")
    with pytest.raises(ProviderError, match="at least 10 active sections"):
        provider.articles(research)

    assert calls == ["research"]


def test_readiness_requires_inherited_section_coverage_before_article_generation() -> None:
    research = SyntheticEditorialProvider().research("2099-01-02")
    retained = {"front", "siyasa_dawla", "iqtisad_flous", "mojtama3", "3adl_7o9o9", "bi2a_manakh", "bniya_transport", "meknes_local", "adab", "history"}
    for section in research["sections"]:
        if section["section_id"] in retained:
            continue
        section.update(
            {
                "status": "NO_NEWS",
                "candidates": [],
                "selected_candidate_id": None,
                "selection_reason": None,
                "no_news_reason": "لا توجد أدلة كافية لنشر مادة في هذا القسم اليوم",
                "fallback_action": "RADAR",
            }
        )
    provider = _configured_readiness_provider()

    with pytest.raises(ProviderError) as caught:
        provider.articles(research)

    assert caught.value.code == "RESEARCH_INSUFFICIENT"
    assert "world_breadth:0/2" in caught.value.detail
    assert "reader_life:0/2" in caught.value.detail
    assert "accountability_and_service:0/2" in caught.value.detail


def test_structurally_ready_research_reaches_article_generation() -> None:
    calls: list[dict] = []
    research = SyntheticEditorialProvider().research("2099-01-02")

    class RecordingProvider(LocalCommandEditorialProvider):
        def _invoke(self, operation: str, payload: dict):
            assert operation == "articles"
            calls.append(payload)
            return SyntheticEditorialProvider().articles(payload["research"])

    provider = _configured_readiness_provider(RecordingProvider)
    articles = provider.articles(research)

    assert len(articles) == len(SECTION_HEADINGS)
    assert len(calls) == 1


def test_repair_receives_complete_original_output_and_preserves_candidate_mapping() -> None:
    research = SyntheticEditorialProvider().research("2099-01-02")
    initial = SyntheticEditorialProvider().articles(research)
    initial[0]["headline"] = None
    repaired = SyntheticEditorialProvider().articles(research)
    calls: list[dict] = []

    class RecordingProvider(LocalCommandEditorialProvider):
        def _invoke(self, operation: str, payload: dict):
            assert operation == "articles"
            calls.append(payload)
            return initial if len(calls) == 1 else repaired

    articles = RecordingProvider(("unused",)).articles(research)

    repair = calls[1]["repair_context"]
    assert repair["validation_error"] == "active section front is incomplete"
    assert repair["previous_articles"] == initial
    assert [item["research_candidate_id"] for item in repair["previous_articles"]] == [
        item["research_candidate_id"] for item in initial
    ]
    assert [item["research_candidate_id"] for item in articles] == [
        item["research_candidate_id"] for item in repaired
    ]


def test_repair_cannot_silently_skip_a_selected_active_article() -> None:
    research = SyntheticEditorialProvider().research("2099-01-02")
    initial = SyntheticEditorialProvider().articles(research)
    repaired = copy.deepcopy(initial)
    repaired[0].update(
        {
            "status": "SKIPPED",
            "skip_reason": "تم حذف المادة من دون بيان سبب قابل للتدقيق",
        }
    )
    provider = LocalCommandEditorialProvider(("unused",))

    with pytest.raises(ProviderError, match="repair changed selected active section"):
        provider._validate_articles(repaired, research, repair_from=initial)

    repaired[0]["repair_skip_reason_code"] = "SOURCE_INVALIDATED"
    assert provider._validate_articles(repaired, research, repair_from=initial)


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
                        "doi": None,
                        "publication_status": "report",
                        "full_text_status": "FULL_TEXT_VERIFIED",
                        "methods_read": True,
                        "limitations_read": True,
                        "science_metadata": None,
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


def test_no_news_is_explicit_and_cannot_create_filler() -> None:
    class NoNewsProvider(LocalCommandEditorialProvider):
        def _invoke(self, operation: str, payload: dict):
            if operation == "research":
                research = SyntheticEditorialProvider().research(payload["edition_date"])
                research["sources"][0].update({
                    "source_type": "primary",
                    "publication_status": "report",
                    "full_text_status": "FULL_TEXT_VERIFIED",
                    "methods_read": True,
                    "limitations_read": True,
                })
                local = next(item for item in research["sections"] if item["section_id"] == "meknes_local")
                local.update({
                    "status": "NO_NEWS",
                    "candidates": [],
                    "selected_candidate_id": None,
                    "selection_reason": None,
                    "no_news_reason": "لم يظهر تطور محلي موثق وجدير بالنشر في نافذة البحث المحددة",
                    "fallback_action": "RADAR",
                })
                return research
            raise AssertionError(operation)

    provider = NoNewsProvider(("unused",))
    research = provider.research("2099-01-02")
    local = next(item for item in research["sections"] if item["section_id"] == "meknes_local")
    assert local["status"] == "NO_NEWS"
    assert local["candidates"] == []

    articles = SyntheticEditorialProvider().articles(research)
    local_article = next(item for item in articles if item["section_id"] == "meknes_local")
    try:
        provider._validate_articles(articles, research)
    except ProviderError as exc:
        assert exc.code == "ARTICLE_SCHEMA_INVALID"
        assert "cannot become an active article" in exc.detail
    else:
        raise AssertionError("no-news research was allowed to become filler")

    local_article.clear()
    local_article.update({
        "section_id": "meknes_local",
        "status": "SKIPPED",
        "skip_reason": "لم يظهر تطور محلي موثق وجدير بالنشر في نافذة البحث المحددة",
    })
    assert provider._validate_articles(articles, research)[9]["status"] == "SKIPPED"


def test_no_news_rejects_placeholder_candidates() -> None:
    class BadNoNewsProvider(LocalCommandEditorialProvider):
        def _invoke(self, operation: str, payload: dict):
            packet = SyntheticEditorialProvider().research(payload["edition_date"])
            local = next(item for item in packet["sections"] if item["section_id"] == "meknes_local")
            local.update({
                "status": "NO_NEWS",
                "selected_candidate_id": None,
                "selection_reason": None,
                "no_news_reason": "لم يظهر تطور محلي موثق وجدير بالنشر في نافذة البحث المحددة",
                "fallback_action": "SKIP",
            })
            return packet

    try:
        BadNoNewsProvider(("unused",)).research("2099-01-02")
    except ProviderError as exc:
        assert exc.code == "RESEARCH_PACKET_INVALID"
        assert "no fabricated candidates" in exc.detail
    else:
        raise AssertionError("no-news decision retained placeholder candidates")


def test_research_rejects_partial_science_metadata() -> None:
    class BadScienceProvider(LocalCommandEditorialProvider):
        def _invoke(self, operation: str, payload: dict):
            packet = SyntheticEditorialProvider().research(payload["edition_date"])
            packet["sources"][0]["science_metadata"] = {"paper_id": "partial"}
            return packet

    try:
        BadScienceProvider(("unused",)).research("2099-01-02")
    except ProviderError as exc:
        assert exc.code == "RESEARCH_PACKET_INVALID"
    else:
        raise AssertionError("partial science passport was accepted")
