#!/usr/bin/env python3
"""Run the configured local editorial provider's unattended health check."""

from __future__ import annotations

import json
from pathlib import Path

from dragon.config import load_local_config
from dragon.providers import LocalCommandEditorialProvider, ProviderError, editorial_provider_from_config


ROOT = Path(__file__).resolve().parent


def main() -> int:
    provider = editorial_provider_from_config(
        load_local_config(ROOT), require_proven=False
    )
    if not isinstance(provider, LocalCommandEditorialProvider):
        print(json.dumps({"status": "FAIL", "error_code": provider.reason}, indent=2))
        return 1
    try:
        result = provider.healthcheck()
    except ProviderError as exc:
        print(json.dumps({"status": "FAIL", "error_code": exc.code, "detail": exc.detail}, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps({"status": "PASS", "provider": result}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
