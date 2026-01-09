"""Read-only consumer preview utilities."""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Iterable, List

from tabulate import tabulate

from .raw_sink import PartitionKey, RawSink
from .state_store import PartitionState


@dataclass
class PartitionPreview:
    partition_key: PartitionKey
    run_id: str
    record_count: int
    sample_rows: List[dict]


def collect_preview(
    sink: RawSink,
    partitions: Iterable[PartitionState],
    sample_rows: int,
) -> List[PartitionPreview]:
    results: List[PartitionPreview] = []
    for state in partitions:
        if not state.current_run_id:
            continue
        key = PartitionKey(
            source=state.source,
            customer_id=state.customer_id,
            query_name=state.query_name,
            logical_date=state.logical_date.isoformat(),
        )
        reader = sink.open_partition(key, state.current_run_id)
        rows = []
        for idx, row in enumerate(reader.iter_payload_rows()):
            rows.append(row)
            if idx + 1 >= sample_rows:
                break
        record_count = state.record_count or len(rows)
        results.append(
            PartitionPreview(
                partition_key=key,
                run_id=state.current_run_id,
                record_count=record_count,
                sample_rows=rows,
            )
        )
    return results


def render_preview(previews: List[PartitionPreview], output_format: str) -> str:
    if not previews:
        return "No authoritative partitions found."
    if output_format == "json":
        payload = [
            {
                "source": preview.partition_key.source,
                "customer_id": preview.partition_key.customer_id,
                "query_name": preview.partition_key.query_name,
                "logical_date": preview.partition_key.logical_date,
                "run_id": preview.run_id,
                "record_count": preview.record_count,
                "sample_rows": preview.sample_rows,
            }
            for preview in previews
        ]
        return json.dumps(payload, indent=2)

    table_data = [
        [
            preview.partition_key.source,
            preview.partition_key.customer_id,
            preview.partition_key.query_name,
            preview.partition_key.logical_date,
            preview.run_id,
            preview.record_count,
            min(len(preview.sample_rows), preview.record_count),
        ]
        for preview in previews
    ]
    headers = [
        "source",
        "customer_id",
        "query_name",
        "logical_date",
        "run_id",
        "record_count",
        "sample_rows",
    ]
    summary = tabulate(table_data, headers=headers, tablefmt="plain")
    samples = "\n\n".join(
        [
            f"{preview.partition_key.query_name} {preview.partition_key.logical_date} sample:\n"
            + json.dumps(preview.sample_rows, indent=2)
            for preview in previews
        ]
    )
    return f"{summary}\n\n{samples}"


__all__ = ["collect_preview", "render_preview"]
