"""Deterministic semantic fixtures for the V5 acquisition classifier."""

from dragon.editorial_functions import classify_event_functions, validated_function_names


def _names(title: str, fact: str) -> set[str]:
    records = classify_event_functions(
        title=title,
        facts=[title, fact],
        evidence_source_ids=["official-page"],
        exact_page_validated=True,
    )
    return validated_function_names({"editorial_functions": records})


def test_accountability_requires_a_concrete_mechanism_and_public_power() -> None:
    assert _names(
        "Audit authority publishes procurement finding",
        "The public audit authority completed an inspection of a municipal procurement contract and referred its finding.",
    ) == {"ACCOUNTABILITY"}


def test_service_requires_a_reader_actionable_change() -> None:
    assert _names(
        "University registration notice",
        "Applicants must register before the 20 September deadline through the stated procedure.",
    ) == {"SERVICE", "READER_VALUE"}


def test_generic_political_policy_announcement_is_not_accountability() -> None:
    assert _names(
        "Government announces a policy",
        "The government announced a broad policy direction at a cabinet meeting and gave no operational detail.",
    ) == set()


def test_airport_statistics_are_not_service() -> None:
    assert _names(
        "Airport passenger statistics rise",
        "The airport reported passenger totals for August and described the annual trend.",
    ) == set()


def test_education_regulation_can_overlap_service_and_reader_value_once() -> None:
    assert _names(
        "Education authority issues admission procedure",
        "The education ministry published eligibility rules and a registration deadline for students applying to the programme.",
    ) == {"SERVICE", "READER_VALUE"}


def test_opinion_criticism_is_not_accountability() -> None:
    assert _names(
        "Opinion: officials must do better",
        "The columnist criticised government performance in general terms and offered a personal recommendation.",
    ) == set()


def test_headline_without_a_separate_exact_page_fact_cannot_close_a_function() -> None:
    assert classify_event_functions(
        title="Audit authority publishes procurement finding",
        facts=["Audit authority publishes procurement finding"],
        evidence_source_ids=["official-page"],
        exact_page_validated=True,
    ) == []
