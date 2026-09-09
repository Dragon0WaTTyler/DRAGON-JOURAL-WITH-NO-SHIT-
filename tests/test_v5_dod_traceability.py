from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
REGISTER = ROOT / "docs" / "V5-DEFINITION-OF-DONE.md"
ROW = re.compile(
    r"^\| (?P<number>\d+) \| .*? \| "
    r"(?P<status>VERIFIED|MACHINE_PASS|PENDING_EXTERNAL|PENDING_HUMAN|PENDING_REAL_RUN) \|"
)


def _rows() -> list[tuple[int, str]]:
    matches = []
    for line in REGISTER.read_text(encoding="utf-8").splitlines():
        match = ROW.match(line)
        if match:
            matches.append((int(match.group("number")), match.group("status")))
    return matches


def test_dod_register_covers_each_requirement_exactly_once() -> None:
    rows = _rows()
    assert [number for number, _ in rows] == list(range(1, 68))


def test_dod_register_keeps_external_and_human_gaps_explicit() -> None:
    pending = {number for number, status in _rows() if status.startswith("PENDING_")}
    assert pending == {3, 37, 39, 50, 62}

    text = REGISTER.read_text(encoding="utf-8")
    assert "must continue to return `BLOCKED`" in text
    assert "no further provider usage is authorized" in text
