#!/usr/bin/env bash
set -euo pipefail

if [[ -z \"${VIRTUAL_ENV:-}\" ]]; then
  echo \"[dev_check] Activate your virtualenv (source .venv/bin/activate) before running this script.\" >&2
  exit 1
fi

python -m compileall src
pip install -e ".[dev]"
python -m pytest
gads-etl --help >/dev/null
python scripts/verify_repo_integrity.py
