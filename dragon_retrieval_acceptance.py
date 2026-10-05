"""Execute or replay a provider-free, bounded research retrieval acceptance trial."""

import argparse
import json
from pathlib import Path
from dragon.retrieval_acceptance import prepare_retrieval, replay_retrieval, run_live_retrieval


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("preflight", "live", "replay"))
    parser.add_argument("--bundle", required=True, type=Path)
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    if args.operation != "replay" and args.receipt is None:
        parser.error("--receipt is required before live retrieval")
    try:
        if args.operation == "replay":
            result = replay_retrieval(args.bundle, root=root)
        elif args.operation == "live":
            result = run_live_retrieval(args.bundle, args.receipt, root=root)
        else:
            replay = prepare_retrieval(args.bundle, args.receipt, root=root)
            result = {**replay["retrieval_preflight"], "selected_action_ids": [a["action_id"] for a in replay["scheduler_allocation"]["actions"]]}
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(json.dumps({"status": "FAIL", "code": getattr(exc, "code", type(exc).__name__), "detail": str(exc)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
