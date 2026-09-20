from dragon.temporal_relevance import evaluate_temporal_relevance
from dragon.deep_research_executor import extract_event_skeleton


EDITION = "2026-09-13"


def _page(**values):
    return {"published_at": values.pop("published_at", "2026-08-24"), "text": values.pop("text", ""), **values}


def test_active_service_window_is_current_even_when_published_earlier() -> None:
    value = evaluate_temporal_relevance(_page(
        effective_start="2026-08-24", effective_end="2026-09-22",
        text="Registration is open from 2026-08-24 through 2026-09-22.",
    ), EDITION)
    assert value["active_on_edition_date"] is True
    assert value["temporal_eligibility_type"] == "ACTIVE_OPERATIONAL_WINDOW"
    assert value["dates"]["EFFECTIVE_END"] == "2026-09-22"


def test_expired_service_deadline_is_not_current() -> None:
    value = evaluate_temporal_relevance(_page(
        deadline="2026-09-08", text="Applications close at the deadline 2026-09-08.",
    ), EDITION)
    assert value["active_on_edition_date"] is False
    assert value["temporal_eligibility_type"] == "EVENT_EXPIRED"
    assert value["rejection_reason"] == "EXPLICIT_DEADLINE_PRECEDES_EDITION_DATE"


def test_arabic_month_deadline_is_expired_after_its_cutoff_not_active_by_publication_month() -> None:
    value = evaluate_temporal_relevance(_page(
        published_at="2026-09-04",
        text="آخر أجل 9 شتنبر 2026 لإيداع الطلبات.",
    ), "2026-09-20")
    assert value["deadline"] == "2026-09-09"
    assert value["active_on_edition_date"] is False
    assert value["temporal_eligibility_type"] == "EVENT_EXPIRED"
    assert value["rejection_reason"] == "EXPLICIT_DEADLINE_PRECEDES_EDITION_DATE"


def test_arabic_month_deadline_is_active_before_its_cutoff() -> None:
    value = evaluate_temporal_relevance(_page(
        published_at="2026-09-04",
        text="آخر أجل 9 شتنبر 2026 لإيداع الطلبات.",
    ), "2026-09-08")
    assert value["deadline"] == "2026-09-09"
    assert value["active_on_edition_date"] is True
    assert value["temporal_eligibility_type"] == "ACTIVE_DEADLINE_WINDOW"


def test_arabic_date_without_a_deadline_label_remains_unresolved() -> None:
    value = evaluate_temporal_relevance(_page(
        published_at="2026-08-24",
        text="يتوفر الدليل الإجرائي المؤرخ في 9 شتنبر 2026.",
    ), EDITION)
    assert value["deadline"] is None
    assert value["active_on_edition_date"] is False
    assert value["temporal_eligibility_type"] == "TEMPORAL_RELEVANCE_UNRESOLVED"


def test_evergreen_guidance_without_operational_dates_is_unresolved() -> None:
    value = evaluate_temporal_relevance(_page(
        published_at="2025-01-01", text="This guide explains how the service generally works.",
    ), EDITION)
    assert value["active_on_edition_date"] is False
    assert value["temporal_eligibility_type"] == "TEMPORAL_RELEVANCE_UNRESOLVED"


def test_active_regulator_period_is_current_accountability_window() -> None:
    value = evaluate_temporal_relevance(_page(
        effective_start="2026-09-10", effective_end="2026-09-22",
        text="The regulator is monitoring electoral violations from 2026-09-10 through 2026-09-22.",
    ), EDITION)
    assert value["active_on_edition_date"] is True
    assert value["temporal_eligibility_type"] == "ACTIVE_OPERATIONAL_WINDOW"


def test_old_regulation_without_new_action_is_not_current_news() -> None:
    value = evaluate_temporal_relevance(_page(
        published_at="2026-02-01", text="The regulation remains legally valid under the standing framework.",
    ), EDITION)
    assert value["active_on_edition_date"] is False
    assert value["rejection_reason"] == "NO_EXPLICIT_ACTIVE_WINDOW"


def test_future_publication_cannot_qualify_retroactively_in_edition_month() -> None:
    value = evaluate_temporal_relevance(_page(
        published_at="2026-09-18",
        text="The regulator published a finding on 2026-09-18.",
    ), EDITION)
    assert value["active_on_edition_date"] is False
    assert value["rejection_reason"] == "PUBLICATION_AFTER_EDITION_DATE"


def test_continuing_event_requires_dated_material_development() -> None:
    value = evaluate_temporal_relevance(_page(
        published_at="2026-05-01", new_development_date="2026-09-12",
        text="Updated enforcement decision announced for the continuing investigation.",
    ), EDITION)
    assert value["active_on_edition_date"] is True
    assert value["temporal_eligibility_type"] == "CONTINUING_EVENT_NEW_DEVELOPMENT"
    assert value["new_development_time"] == "2026-09-12"


def test_undated_continuing_language_does_not_qualify() -> None:
    value = evaluate_temporal_relevance(_page(
        published_at="2026-05-01", text="An ongoing framework remains legally valid.",
    ), EDITION)
    assert value["active_on_edition_date"] is False


def test_event_extractor_keeps_explicit_active_window_in_skeleton() -> None:
    skeleton = extract_event_skeleton({
        "title": "University registration remains open",
        "title_state": "TITLE_RESOLVED",
        "published_at": "2026-08-24",
        "text": "The university registration procedure is open from 2026-08-24 through 2026-09-22 for eligible applicants. " * 8,
    }, {"event_context": {"research_date": EDITION}})
    assert skeleton["state"] == "CONCRETE_EVENT"
    assert skeleton["temporal_relevance"]["temporal_eligibility_type"] == "ACTIVE_OPERATIONAL_WINDOW"
