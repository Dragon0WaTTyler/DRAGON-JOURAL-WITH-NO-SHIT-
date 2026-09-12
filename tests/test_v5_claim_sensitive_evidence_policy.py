"""Offline red-team checks for claim-sensitive evidence requirements."""

from dragon.evidence_policy import candidate_evidence_policy


def _candidate(title: str, fact: str, *, primary: bool = True, claim_type: str | None = None) -> tuple[dict, dict]:
    source = {"p": {"source_type": "official"}} if primary else {}
    candidate = {"title": title, "facts": [fact], "claims": [], "primary_evidence_source_ids": ["p"] if primary else [], "independent_evidence_source_ids": []}
    if claim_type:
        candidate["claim_type"] = claim_type
    return candidate, source


def test_ministry_announcement_and_operator_timetable_can_use_exact_primary_source() -> None:
    for title, fact in (("وزارة تعلن الموعد", "أعلنت الوزارة الموعد الرسمي."), ("Schedule", "Operator timetable and service schedule.")):
        candidate, sources = _candidate(title, fact)
        assert candidate_evidence_policy(candidate, sources)["required_roles"] == ["PRIMARY"]


def test_impact_claim_allegation_science_and_opinion_premises_do_not_get_the_exception() -> None:
    fixtures = [
        ("Economic impact", "The announcement will have major economic impact."),
        ("اتهام بالفساد", "اتهام بالفساد لم يثبت."),
        ("Scientific result", "Official announcement of scientific result."),
        ("Opinion", "This opinion asserts a factual premise without a direct source."),
    ]
    for title, fact in fixtures:
        candidate, sources = _candidate(title, fact)
        section = "science" if title == "Scientific result" else None
        assert candidate_evidence_policy(candidate, sources, section_id=section)["required_roles"] == ["PRIMARY", "INDEPENDENT"]


def test_audit_finding_is_not_criminal_guilt_and_syndication_cannot_supply_independence() -> None:
    audit, sources = _candidate("Audit report", "Official audit report documents an irregularity.")
    assert candidate_evidence_policy(audit, sources)["required_roles"] == ["PRIMARY"]
    guilt, sources = _candidate("Audit proves guilt", "The audit proves criminal guilt.")
    assert candidate_evidence_policy(guilt, sources)["risky_claim_protection"] is True
