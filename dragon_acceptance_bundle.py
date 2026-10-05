"""Prove, discover, verify, or replay local acceptance archives without AI calls."""

import argparse
import json
from pathlib import Path

from dragon.acceptance_replay import replay_acceptance_bundle
from dragon.contract_replay import preserve_contract_comparison
from dragon.archive import acceptance_archive_root, discover_acceptance_bundles, prove_acceptance_archive, verify_acceptance_bundle
from dragon.state import atomic_write_json, sha256_file


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("prove", "discover", "verify", "replay", "compare-contract"))
    parser.add_argument("--bundle", type=Path)
    parser.add_argument("--archive-root", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    try:
        destination = acceptance_archive_root(root, args.archive_root)
        if args.operation == "prove":
            result = prove_acceptance_archive(root, destination)
        elif args.operation == "discover":
            result = {"bundles": [str(path) for path in discover_acceptance_bundles(destination)]}
        else:
            if args.bundle is None:
                parser.error("--bundle is required for verify/replay/compare-contract")
            if args.operation == "verify":
                manifest = verify_acceptance_bundle(args.bundle)
                result = {"status": "PASS", "run_id": manifest["run_id"], "artifacts": len(manifest["artifacts"]),
                    "manifest_sha256": sha256_file(args.bundle / "manifest.json")}
            elif args.operation == "compare-contract":
                result = preserve_contract_comparison(args.bundle, code_root=root,
                    destination=destination / "contract-comparisons")
            else:
                result = replay_acceptance_bundle(args.bundle, code_root=root)
                result["manifest_sha256"] = sha256_file(args.bundle / "manifest.json")
                report = args.bundle.parent / "replay-reports" / f"{result['run_id']}-{result['manifest_sha256']}.json"
                if report.exists() and json.loads(report.read_text(encoding="utf-8")) != result:
                    raise ValueError("existing replay receipt differs; preserved without overwrite")
                if not report.exists():
                    atomic_write_json(report, result)
                result = {**result, "receipt": str(report)}
        print(json.dumps(result, ensure_ascii=False))
        return 1 if result.get("FRESH_LIVE_REPLAY") == "FAIL" else 0
    except Exception as exc:
        print(json.dumps({"status": "FAIL", "code": getattr(exc, "code", type(exc).__name__), "detail": str(exc)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
