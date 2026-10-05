"""Bounded render-detect-repair-compare policy for PDF presentation only."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from dragon.state import sha256_file


def apply_layout_doctor(
    pdf_path: Path,
    initial_report: dict,
    *,
    render: Callable[[int], None],
    inspect: Callable[[], dict],
    baseline_line_height: int = 29,
    candidate_line_height: int = 34,
) -> tuple[dict, dict]:
    """Try one safe spacing change; keep only a PASS, otherwise restore exact bytes."""
    baseline_hash = sha256_file(pdf_path)
    doctor = {
        "status": "PASS" if initial_report.get("status") == "PASS" else "FAIL",
        "policy": "LEAST_INTRUSIVE_SAFE_REFLOW",
        "editorial_inputs_immutable": True,
        "initial_line_height": baseline_line_height,
        "candidate_line_height": candidate_line_height,
        "action": "KEEP" if initial_report.get("status") == "PASS" else "BLOCK_UNSAFE_DEFECT",
        "before_sha256": baseline_hash,
        "after_sha256": baseline_hash,
        "before_issues": list(initial_report.get("issues", [])),
        "candidate_issues": None,
        "after_issues": list(initial_report.get("issues", [])),
    }
    if initial_report.get("status") == "PASS":
        return initial_report, doctor
    sparse_only = bool(initial_report.get("issues")) and all(
        issue.startswith("PDF_SPARSE_PAGE:") for issue in initial_report["issues"]
    )
    if not sparse_only:
        return initial_report, doctor

    render(candidate_line_height)
    candidate_report = inspect()
    doctor["candidate_issues"] = list(candidate_report.get("issues", []))
    if candidate_report.get("status") == "PASS":
        doctor.update({
            "status": "PASS",
            "action": "KEEP_SAFE_SPACING_REPAIR",
            "after_sha256": sha256_file(pdf_path),
            "after_issues": [],
        })
        return candidate_report, doctor

    render(baseline_line_height)
    reverted_report = inspect()
    reverted_hash = sha256_file(pdf_path)
    doctor.update({
        "status": "FAIL",
        "action": "REVERT_AND_BLOCK",
        "after_sha256": reverted_hash,
        "after_issues": list(reverted_report.get("issues", [])),
        "revert_exact": reverted_hash == baseline_hash,
    })
    if reverted_hash != baseline_hash:
        doctor["after_issues"].append("LAYOUT_REVERT_HASH_MISMATCH")
    return reverted_report, doctor
