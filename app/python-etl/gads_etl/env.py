"""Utility wrappers for loading .env files with helpful errors."""
from __future__ import annotations


def load_env(*args, **kwargs):
    """Proxy to python-dotenv that surfaces actionable errors when missing."""
    try:
        from dotenv import load_dotenv as _load_dotenv
    except ModuleNotFoundError as exc:  # pragma: no cover - dependency missing
        raise RuntimeError(
            "python-dotenv is not installed. Install project dependencies with "
            "`uv sync --extra dev` or `pip install -e '.[dev]'` before running commands."
        ) from exc
    return _load_dotenv(*args, **kwargs)


__all__ = ["load_env"]
