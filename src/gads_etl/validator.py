"""Loader/validator that assigns authority to raw partitions."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from .raw_sink import PartitionKey, RawSink
from .state_store import PartitionState, PartitionStateRepository


class RawPartitionValidator:
    """Validates raw partitions and records status in the state store."""

    def __init__(
        self,
        raw_sink: RawSink,
        state_repo: PartitionStateRepository,
    ) -> None:
        self.raw_sink = raw_sink
        self.state_repo = state_repo
        self.state_repo.ensure_schema()

    def validate_partition(
        self,
        partition_key: PartitionKey,
        run_id: str,
    ) -> PartitionState:
        """Validate payload/metadata and upsert partition state."""
        try:
            reader = self.raw_sink.open_partition(partition_key, run_id)
        except FileNotFoundError as exc:
            return self._record_failure(
                partition_key,
                f"Partition not found: {exc}",
            )

        try:
            metadata = reader.read_metadata()
        except Exception as exc:  # pragma: no cover - unexpected parsing errors
            return self._record_failure(partition_key, f"Metadata read failed: {exc}")

        try:
            rows = list(reader.iter_payload_rows())
        except Exception as exc:  # pragma: no cover
            return self._record_failure(partition_key, f"Payload read failed: {exc}")

        record_count = int(metadata.get("record_count", len(rows)))
        if record_count != len(rows):
            return self._record_failure(
                partition_key,
                f"Record count mismatch: metadata={record_count} actual={len(rows)}",
            )

        return self._record_success(partition_key, run_id, record_count)

    def _record_success(
        self, partition_key: PartitionKey, run_id: str, record_count: int
    ) -> PartitionState:
        previous = self._fetch_state(partition_key)
        logical_date = datetime.fromisoformat(partition_key.logical_date).date()
        selected_run_id = run_id
        selected_count = record_count
        schema_version = "v1"
        if previous and previous.current_run_id:
            if self._compare_run_ids(run_id, previous.current_run_id) < 0:
                # Older run finished after a newer one; retain existing authority.
                selected_run_id = previous.current_run_id
                selected_count = previous.record_count or selected_count
                schema_version = previous.schema_version or schema_version
            else:
                schema_version = "v1"
        state = PartitionState(
            source=partition_key.source,
            customer_id=partition_key.customer_id,
            query_name=partition_key.query_name,
            logical_date=logical_date,
            status="success",
            current_run_id=selected_run_id,
            schema_version=schema_version,
            record_count=selected_count,
            updated_at=self._now(),
            error_message=None,
            attempt_count=(previous.attempt_count + 1) if previous else 1,
        )
        self.state_repo.upsert_partition_state(state)
        return state

    def _record_failure(self, partition_key: PartitionKey, message: str) -> PartitionState:
        previous = self._fetch_state(partition_key)
        state = PartitionState(
            source=partition_key.source,
            customer_id=partition_key.customer_id,
            query_name=partition_key.query_name,
            logical_date=datetime.fromisoformat(partition_key.logical_date).date(),
            status="failed",
            current_run_id=previous.current_run_id if previous else None,
            schema_version=previous.schema_version if previous else None,
            record_count=previous.record_count if previous else None,
            updated_at=self._now(),
            error_message=message,
            attempt_count=(previous.attempt_count + 1) if previous else 1,
        )
        self.state_repo.upsert_partition_state(state)
        return state

    def _fetch_state(self, partition_key: PartitionKey) -> Optional[PartitionState]:
        return self.state_repo.get_partition_state(
            source=partition_key.source,
            customer_id=partition_key.customer_id,
            query_name=partition_key.query_name,
            logical_date=datetime.fromisoformat(partition_key.logical_date).date(),
        )

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def _compare_run_ids(candidate: str, existing: str) -> int:
        """Return negative if candidate < existing, zero if equal, positive if greater."""
        return (candidate > existing) - (candidate < existing)


__all__ = ["RawPartitionValidator"]
