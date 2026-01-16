"""Pytest configuration for loading local environment variables."""
from __future__ import annotations

from pathlib import Path
import os
import sys

try:
    from gads_etl.env import load_env
except ImportError as exc:
    raise RuntimeError(
        "gads_etl is not importable. Activate your virtualenv (source .venv/bin/activate) "
        "and run 'pip install -e .' before running pytest."
    ) from exc

venv = os.environ.get("VIRTUAL_ENV")
if not venv or not Path(venv).exists():
    raise RuntimeError(
        "You are running pytest outside the project virtualenv. "
        "Activate it with 'source .venv/bin/activate' and run 'python -m pytest'."
    )
if not Path(venv).resolve().samefile(Path(sys.prefix).resolve()):
    raise RuntimeError(
        "You are running pytest from a different interpreter. "
        "Activate your venv and run: python -m pytest"
    )

# Load default runtime env first, then overlay .env.test if provided
load_env()
test_env = Path(".env.test")
if test_env.exists():
    load_env(dotenv_path=test_env, override=True)
