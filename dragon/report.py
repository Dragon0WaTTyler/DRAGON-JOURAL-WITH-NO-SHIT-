"""Machine-readable and concise human run reporting."""

from __future__ import annotations

from datetime import date, datetime, time
import json
import os
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

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


def _read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def collect_operational_metrics(root: Path, run_dir: Path, state: dict) -> dict:
    date_value = state["date"]
    edition = root / "editions" / date_value[:4] / date_value[5:7] / date_value
    intelligence = _read_json(run_dir / "source-intelligence" / "report.json")
    monitoring = _read_json(run_dir / "source-monitoring" / "report.json")
    claim_graph = _read_json(run_dir / "evidence" / "claim-graph.json")
    arabic = _read_json(run_dir / "qa" / "arabic-language.json")
    pdf = _read_json(run_dir / "qa" / "pdf.json")
    pdf_visual = _read_json(run_dir / "qa" / "pdf-visual.json")
    epub = _read_json(run_dir / "qa" / "epub.json")
    epubcheck = _read_json(run_dir / "qa" / "epubcheck.json")
    cover = _read_json(edition / "cover-brief.json")
    layout = _read_json(edition / "layout-plan.json")
    archive = _read_json(run_dir / "archive-receipt.json")
    delivery = _read_json(run_dir / "delivery-receipt.json")
    claims = claim_graph.get("claims", [])
    origins = {
        origin
        for event in intelligence.get("event_clusters", [])
        for origin in event.get("independent_origin_groups", [])
    }
    return {
        "source_count": intelligence.get("summary", {}).get("source_count"),
        "watched_target_count": monitoring.get("summary", {}).get("enabled"),
        "changed_target_count": monitoring.get("summary", {}).get("changed"),
        "source_monitoring": monitoring.get("status", "NOT_PRESENT"),
        "publisher_count": len({
            item.get("publisher") for item in intelligence.get("source_records", [])
            if item.get("publisher")
        }),
        "independent_origin_count": len(origins),
        "event_count": intelligence.get("summary", {}).get("event_count"),
        "claim_count": len(claims),
        "unsupported_claim_count": sum(
            item.get("assessment") in {"UNAVAILABLE", "CONTRADICTED"} for item in claims
        ),
        "arabic_qa": arabic.get("status", "NOT_PRESENT"),
        "cover_mode": cover.get("mode"),
        "cover_qa": "PASS" if cover.get("accepted") else "NOT_PRESENT",
        "layout_qa": layout.get("status", "NOT_PRESENT"),
        "pdf_qa": pdf.get("status", "NOT_PRESENT"),
        "pdf_visual_qa": pdf_visual.get("status", "NOT_PRESENT"),
        "epub_qa": epub.get("status", "NOT_PRESENT"),
        "epubcheck": epubcheck.get("status", "NOT_PRESENT"),
        "remote_readback": (
            "PASS" if archive.get("verified") is True else archive.get("status", "NOT_PRESENT")
        ),
        "delivery_receipt": delivery.get("status", "NOT_PRESENT"),
    }


def evaluate_deadlines(state: dict, timezone: str, target_deadline: str | None) -> dict:
    if not target_deadline:
        return {
            "target_deadline": None,
            "publication_deadline_status": "NOT_CONFIGURED",
            "delivery_deadline_status": "NOT_CONFIGURED",
        }
    try:
        target = datetime.combine(
            date.fromisoformat(state["date"]),
            time.fromisoformat(target_deadline),
            tzinfo=ZoneInfo(timezone),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("TARGET_DEADLINE_INVALID") from exc

    def outcome(stage_name: str, completed: bool) -> str:
        ended_at = state.get("stages", {}).get(stage_name, {}).get("ended_at")
        if not completed or not ended_at:
            return "NOT_COMPLETED"
        try:
            ended = datetime.fromisoformat(ended_at)
        except (TypeError, ValueError):
            return "UNKNOWN"
        return "ON_TIME" if ended <= target else "LATE"

    return {
        "target_deadline": target.isoformat(),
        "publication_deadline_status": outcome(
            "final_qa", state.get("publication_status") == "COMPLETE"
        ),
        "delivery_deadline_status": outcome(
            "whatsapp_delivery", state.get("delivery_status") == "COMPLETE"
        ),
    }


def finalize_report(
    root: Path,
    run_dir: Path,
    state: dict,
    timezone: str,
    target_deadline: str | None = None,
) -> tuple[Path, Path]:
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
    cover_status = state["stages"].get("cover", {}).get("status", "NOT_PRESENT")
    cover_brief = root / "editions" / state["date"][:4] / state["date"][5:7] / state["date"] / "cover-brief.json"
    try:
        cover_value = json.loads(cover_brief.read_text(encoding="utf-8"))
        cover_status = cover_value.get("cover_status", cover_status)
    except (OSError, ValueError):
        pass
    report = {
        "schema_version": 5,
        "date": state["date"],
        "run_id": state["run_id"],
        "trigger": state.get("trigger"),
        "trigger_time": state["started_at"],
        "resume_or_new": state.get("invocation", "UNKNOWN"),
        "runtime_fingerprint": state.get("runtime_fingerprint"),
        "result": state["run_result"],
        "started_at": state["started_at"],
        "ended_at": ended,
        "duration_seconds": round(_duration_seconds(state["started_at"], ended), 3),
        "publication": state["publication_status"],
        "cover": cover_status,
        "pdf": state["stages"].get("pdf", {}).get("status", "NOT_PRESENT"),
        "epub": state["stages"].get("epub", {}).get("status", "NOT_PRESENT"),
        "archive": state["archive_status"],
        "whatsapp": state["delivery_status"],
        "recovery_actions": recoveries,
        "warnings": warnings,
        "last_successful_checkpoint": state.get("last_successful_checkpoint"),
        "error_code": state.get("error_code"),
        "operational_metrics": collect_operational_metrics(root, run_dir, state),
        "stage_receipts": [
            {
                "stage": name,
                "status": record["status"],
                "started_at": record.get("started_at"),
                "ended_at": record.get("ended_at"),
                "duration_seconds": _duration_seconds(record.get("started_at"), record.get("ended_at")),
                "attempts": record.get("attempt_count", 0),
                "failure_code": record.get("error_code"),
                "fallbacks": record.get("recovery_history", []),
                "input_hashes": record.get("input_hashes", {}),
                "output_hashes": record.get("artifact_hashes", {}),
            }
            for name, record in state["stages"].items()
        ],
        **evaluate_deadlines(state, timezone, target_deadline),
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
        f"Deadline: publication={report['publication_deadline_status']} | delivery={report['delivery_deadline_status']}",
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
