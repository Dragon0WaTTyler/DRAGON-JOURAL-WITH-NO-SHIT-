"""Offline finality audit/replay; this command has no live integration."""

import argparse
import json
from pathlib import Path

from dragon.research_finality_acceptance import preserve_finality_review, replay_finality_review


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    review = commands.add_parser("review")
    for name in ("provider", "retrieval", "evidence-review"):
        review.add_argument("--" + name, required=True, type=Path)
    review.add_argument("--root", type=Path, default=Path(__file__).resolve().parent)
    replay = commands.add_parser("replay")
    replay.add_argument("bundle", type=Path)
    args = parser.parse_args()
    result = replay_finality_review(args.bundle) if args.command == "replay" else preserve_finality_review(
        args.provider, args.retrieval, args.evidence_review, root=args.root)
    print(json.dumps(result, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
