"""Per-stage structured logs without secret-bearing environment dumps."""

from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


class StageLogger:
    def __init__(self, path: Path, timezone: str):
        self.path = path
        self.timezone = timezone
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, event: str, **fields: Any) -> None:
        record = {
            "timestamp": datetime.now(ZoneInfo(self.timezone)).isoformat(),
            "event": event,
            **fields,
        }
        with self.path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
