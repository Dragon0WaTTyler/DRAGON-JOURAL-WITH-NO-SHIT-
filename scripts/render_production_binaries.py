#!/usr/bin/env python3
"""Compatibility CLI: validate/render only; never claim remote publication."""
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.publication_renderer import render
if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--date', required=True)
    args = parser.parse_args()
    print(json.dumps(render(Path(__file__).resolve().parents[1], args.date), indent=2))
