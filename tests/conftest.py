"""Pytest configuration for loading local environment variables."""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = PROJECT_ROOT / "app/python-etl"
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from gads_etl.env import load_env

# Load default runtime env first, then overlay .env.test if provided
load_env()
test_env = Path(".env.test")
if test_env.exists():
    load_env(dotenv_path=test_env, override=True)
