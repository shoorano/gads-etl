"""Vendor-neutral interfaces for raw sink implementations."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, Protocol, Sequence


@dataclass(frozen=True)
class PartitionKey:
    """Identity of a logical partition."""

    source: str
    customer_id: str
    query_name: str
    logical_date: str  # YYYY-MM-DD


class PartitionWriter(Protocol):
    """Mutable handle for writing exactly one raw partition."""

    def write_payload_row(self, row: Mapping[str, object]) -> None:
        """Append a JSON-serializable row destined for payload.jsonl."""

    def finalize(self, metadata: Mapping[str, object]) -> None:
        """Persist metadata.json and mark the partition immutable."""


class PartitionReader(Protocol):
    """Read-only handle for an immutable raw partition."""

    def iter_payload_rows(self) -> Iterable[Mapping[str, object]]:
        """Yield payload rows in the order they were stored."""

    def read_metadata(self) -> Mapping[str, object]:
        """Return metadata.json contents."""


class RawSink(Protocol):
    """Backend interface used by extractors/validators to interact with raw storage."""

    def write_partition(self, partition_key: PartitionKey, run_id: str) -> PartitionWriter:
        """Return a writer scoped to (partition_key, run_id)."""

    def open_partition(self, partition_key: PartitionKey, run_id: str) -> PartitionReader:
        """Return a reader for the given partition; raises if it does not exist."""

    def list_partitions(self, partition_key: PartitionKey) -> Sequence[str]:
        """Return the available run_ids for the partition key."""


__all__ = [
    "PartitionKey",
    "PartitionWriter",
    "PartitionReader",
    "RawSink",
]
