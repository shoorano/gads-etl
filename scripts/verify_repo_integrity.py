#!/usr/bin/env python
"""Fail-fast import verification for critical modules."""
from __future__ import annotations

import importlib
import os
import sys

MODULES = [
    "gads_etl",
    "gads_etl.cli",
    "gads_etl.pipeline",
    "gads_etl.raw_sink",
    "gads_etl.raw_sink_local",
    "gads_etl.raw_sink_object",
    "gads_etl.raw_sink_factory",
    "gads_etl.state_store",
]


def main() -> int:
    if not os.getenv("VIRTUAL_ENV"):
        print(
            "[verify_repo_integrity] Must run inside activated virtualenv (source .venv/bin/activate).",
            file=sys.stderr,
        )
        return 1
    for module in MODULES:
        try:
            importlib.import_module(module)
        except Exception as exc:  # pragma: no cover - intentional fail fast
            print(f"[verify_repo_integrity] Failed to import {module}: {exc}", file=sys.stderr)
            return 1
    print("[verify_repo_integrity] All modules imported successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
