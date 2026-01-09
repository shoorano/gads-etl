"""Helpers for formatting partition state inspection output."""
from __future__ import annotations

import json
from typing import Iterable, List

from tabulate import tabulate

from .state_store import PartitionState


def format_states(states: Iterable[PartitionState], output_format: str = "table") -> str:
    rows = list(states)
    if not rows:
        return "No partition state records found."
    if output_format == "json":
        payload: List[dict] = [
            {
                "source": row.source,
                "customer_id": row.customer_id,
                "query_name": row.query_name,
                "logical_date": row.logical_date.isoformat(),
                "status": row.status,
                "current_run_id": row.current_run_id,
                "schema_version": row.schema_version,
                "record_count": row.record_count,
                "updated_at": row.updated_at.isoformat(),
                "error_message": row.error_message,
                "attempt_count": row.attempt_count,
            }
            for row in rows
        ]
        return json.dumps(payload, indent=2)

    table_data = [
        [
            row.source,
            row.customer_id,
            row.query_name,
            row.logical_date.isoformat(),
            row.status,
            row.current_run_id or "-",
            row.record_count if row.record_count is not None else "-",
            row.updated_at.isoformat(),
        ]
        for row in rows
    ]
    headers = [
        "source",
        "customer_id",
        "query_name",
        "logical_date",
        "status",
        "current_run_id",
        "record_count",
        "updated_at",
    ]
    return tabulate(table_data, headers=headers, tablefmt="plain")


__all__ = ["format_states"]
