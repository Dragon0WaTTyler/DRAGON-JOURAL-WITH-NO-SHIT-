#!/usr/bin/env python3
"""Build a read-only source coverage inventory from the committed registry."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml

from dragon.source_coverage import build_source_coverage_report, load_source_coverage, probe_source_routes
from dragon.providers import SECTION_HEADINGS


ROOT = Path(__file__).resolve().parent


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", default=None, help="edition date for report metadata")
    parser.add_argument("--run-id", default=None, help="optional fresh run identifier")
    parser.add_argument("--output", help="report JSON path")
    parser.add_argument("--probe", action="store_true", help="perform bounded public HEAD health checks")
    args = parser.parse_args()
    path = ROOT / "config" / "source-coverage.yaml"
    coverage = load_source_coverage(path, {section_id for section_id, _ in SECTION_HEADINGS})
    health = probe_source_routes(coverage) if args.probe else None
    report = build_source_coverage_report(coverage, edition_date=args.date, run_id=args.run_id, route_health=health)
    output = Path(args.output).resolve() if args.output else ROOT / "acceptance" / "source-coverage" / (args.date or "unbound") / "source-coverage-report.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "PASS", "output": str(output.relative_to(ROOT)).replace("\\", "/"), "configured_sources": report["configured_source_count"], "active_sources": report["active_source_count"], "active_routes": report["active_route_count"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
