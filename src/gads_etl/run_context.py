"""Execution metadata for a pipeline run."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


def _current_run_id() -> str:
    """Return ISO-8601 UTC timestamp with millisecond precision."""
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


@dataclass(frozen=True)
class RunContext:
    """Carries identifiers for a single pipeline execution attempt."""

    run_id: str

    @classmethod
    def create(cls) -> "RunContext":
        """Instantiate a new context with a freshly generated run_id."""
        return cls(run_id=_current_run_id())


__all__ = ["RunContext"]
