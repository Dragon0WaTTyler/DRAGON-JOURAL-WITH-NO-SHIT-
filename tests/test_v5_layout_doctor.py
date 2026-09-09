from pathlib import Path

from dragon.layout_doctor import apply_layout_doctor
from dragon.state import sha256_file


def _report(*issues: str) -> dict:
    return {"status": "FAIL" if issues else "PASS", "issues": list(issues)}


def test_layout_doctor_keeps_passing_safe_spacing_candidate(tmp_path: Path) -> None:
    pdf = tmp_path / "edition.pdf"
    pdf.write_bytes(b"baseline")

    def render(line_height: int) -> None:
        pdf.write_bytes(f"render-{line_height}".encode())

    def inspect() -> dict:
        return _report() if pdf.read_bytes() == b"render-34" else _report("PDF_SPARSE_PAGE:2")

    report, doctor = apply_layout_doctor(
        pdf, _report("PDF_SPARSE_PAGE:2"), render=render, inspect=inspect
    )
    assert report["status"] == "PASS"
    assert doctor["action"] == "KEEP_SAFE_SPACING_REPAIR"
    assert doctor["editorial_inputs_immutable"] is True
    assert doctor["after_sha256"] == sha256_file(pdf)


def test_layout_doctor_reverts_failed_candidate_to_exact_baseline(tmp_path: Path) -> None:
    pdf = tmp_path / "edition.pdf"
    pdf.write_bytes(b"render-29")
    baseline = sha256_file(pdf)

    def render(line_height: int) -> None:
        pdf.write_bytes(f"render-{line_height}".encode())

    report, doctor = apply_layout_doctor(
        pdf,
        _report("PDF_SPARSE_PAGE:2"),
        render=render,
        inspect=lambda: _report("PDF_SPARSE_PAGE:2"),
    )
    assert report["status"] == "FAIL"
    assert doctor["action"] == "REVERT_AND_BLOCK"
    assert doctor["revert_exact"] is True
    assert sha256_file(pdf) == baseline


def test_layout_doctor_does_not_mutate_non_spacing_defect(tmp_path: Path) -> None:
    pdf = tmp_path / "edition.pdf"
    pdf.write_bytes(b"baseline")
    calls = []
    report, doctor = apply_layout_doctor(
        pdf,
        _report("PDF_CANONICAL_COVER_MISMATCH"),
        render=lambda value: calls.append(value),
        inspect=lambda: _report(),
    )
    assert report["status"] == "FAIL"
    assert doctor["action"] == "BLOCK_UNSAFE_DEFECT"
    assert calls == []
