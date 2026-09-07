"""Machine-readable and concise human run reporting."""

from __future__ import annotations

from datetime import datetime
import os
from pathlib import Path
from uuid import uuid4

from dragon.state import atomic_write_json, now_iso


def _duration_seconds(started: str, ended: str) -> float:
    try:
        return max(0.0, (datetime.fromisoformat(ended) - datetime.fromisoformat(started)).total_seconds())
    except (TypeError, ValueError):
        return 0.0


def _atomic_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as stream:
            stream.write(value)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def finalize_report(root: Path, run_dir: Path, state: dict, timezone: str) -> tuple[Path, Path]:
    ended = now_iso(timezone)
    state["ended_at"] = ended
    if not state.get("run_result"):
        stage_statuses = [record["status"] for record in state["stages"].values()]
        if any(value == "FAILED" for value in stage_statuses):
            state["run_result"] = "FAILED"
        elif any(value == "BLOCKED" for value in stage_statuses):
            state["run_result"] = "BLOCKED"
        elif state.get("publication_status") == "COMPLETE" and any(
            value == "DEGRADED" for value in stage_statuses
        ):
            state["run_result"] = "DEGRADED"
        elif all(value == "COMPLETE" for value in stage_statuses):
            state["run_result"] = "COMPLETE"
        else:
            state["run_result"] = "INCOMPLETE"
    recoveries = sum(len(record.get("recovery_history", [])) for record in state["stages"].values())
    warnings = [
        {"stage": name, "status": record["status"], "error_code": record.get("error_code")}
        for name, record in state["stages"].items()
        if record["status"] in {"DEGRADED", "FAILED", "BLOCKED"}
    ]
    report = {
        "schema_version": 5,
        "date": state["date"],
        "run_id": state["run_id"],
        "result": state["run_result"],
        "started_at": state["started_at"],
        "ended_at": ended,
        "duration_seconds": round(_duration_seconds(state["started_at"], ended), 3),
        "publication": state["publication_status"],
        "cover": state["stages"].get("cover", {}).get("status", "NOT_PRESENT"),
        "pdf": state["stages"].get("pdf", {}).get("status", "NOT_PRESENT"),
        "epub": state["stages"].get("epub", {}).get("status", "NOT_PRESENT"),
        "archive": state["archive_status"],
        "whatsapp": state["delivery_status"],
        "recovery_actions": recoveries,
        "warnings": warnings,
        "last_successful_checkpoint": state.get("last_successful_checkpoint"),
        "error_code": state.get("error_code"),
    }
    json_path = run_dir / "run-report.json"
    text_path = run_dir / "run-report.txt"
    atomic_write_json(json_path, report)
    lines = [
        f"DRAGON V5 — {report['date']}",
        f"Result: {report['result']}",
        f"Duration: {report['duration_seconds']:.3f}s",
        f"Publication: {report['publication']} | Cover: {report['cover']} | PDF: {report['pdf']} | EPUB: {report['epub']}",
        f"Archive: {report['archive']} | WhatsApp: {report['whatsapp']}",
        f"Recovery actions: {report['recovery_actions']}",
    ]
    if warnings:
        lines.append("Warnings: " + ", ".join(f"{item['stage']}={item['status']}" for item in warnings))
    if report["error_code"]:
        lines.append(f"Error: {report['error_code']}")
    _atomic_text(text_path, "\n".join(lines) + "\n")
    state["report_paths"] = [
        str(json_path.relative_to(root)).replace("\\", "/"),
        str(text_path.relative_to(root)).replace("\\", "/"),
    ]
    return json_path, text_path
