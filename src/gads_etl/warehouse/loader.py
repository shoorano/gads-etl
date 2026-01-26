"""Warehouse loader abstractions per docs/warehouse_semantics.md."""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, Tuple

from ..state_store import PartitionStateRepository
from .pointer_store import WarehousePointer, WarehousePointerStore


@dataclass(frozen=True)
class LogicalPartitionTarget:
    """Represents a logical partition that requires warehouse action."""

    source: str
    customer_id: str
    query_name: str
    logical_date: str  # YYYY-MM-DD
    run_id: str
    schema_version: Optional[str]


@dataclass(frozen=True)
class ReconciliationPlan:
    """Immutable lists of partitions to load or replace."""

    load: Tuple[LogicalPartitionTarget, ...]
    replace: Tuple[LogicalPartitionTarget, ...]
    demote: Tuple[WarehousePointer, ...]


class WarehouseLoader:
    """Placeholder loader honoring docs/warehouse_semantics.md contract."""

    def __init__(
        self,
        partition_state_repository: PartitionStateRepository,
        pointer_store: WarehousePointerStore,
    ):
        """Initialize the loader with read-only dependencies."""
        self._partition_state_repository = partition_state_repository
        self._pointer_store = pointer_store

    def run(self) -> ReconciliationPlan:
        """Drive warehouse loading as defined in docs/warehouse_semantics.md."""
        plan = self._reconcile_partitions()
        self._publish(plan)
        self._demote(plan)
        return plan

    def _reconcile_partitions(self) -> ReconciliationPlan:
        """Compare PartitionState with warehouse pointers to find work."""
        states = self._partition_state_repository.list_partition_states(
            status="success"
        )
        load_targets = []
        replace_targets = []
        success_keys = set()

        for state in states:
            current_run_id = state.current_run_id
            if not current_run_id:
                continue
            logical_date = state.logical_date.isoformat()
            key = (
                state.source,
                state.customer_id,
                state.query_name,
                logical_date,
            )
            success_keys.add(key)
            pointer = self._pointer_store.get_pointer(
                state.source,
                state.customer_id,
                state.query_name,
                logical_date,
            )
            target = LogicalPartitionTarget(
                source=state.source,
                customer_id=state.customer_id,
                query_name=state.query_name,
                logical_date=logical_date,
                run_id=current_run_id,
                schema_version=state.schema_version,
            )
            if pointer is None:
                load_targets.append(target)
                continue
            if pointer.run_id != current_run_id:
                replace_targets.append(target)

        demotions = []
        for pointer in self._pointer_store.list_pointers():
            key = (
                pointer.source,
                pointer.customer_id,
                pointer.query_name,
                pointer.logical_date,
            )
            if key not in success_keys:
                demotions.append(pointer)

        return ReconciliationPlan(
            load=tuple(load_targets),
            replace=tuple(replace_targets),
            demote=tuple(demotions),
        )

    def _publish(self, plan: ReconciliationPlan) -> None:
        """Publish reconciled partitions by updating warehouse pointers."""
        now_iso = datetime.now(timezone.utc).isoformat()
        for target in (*plan.load, *plan.replace):
            pointer = WarehousePointer(
                source=target.source,
                customer_id=target.customer_id,
                query_name=target.query_name,
                logical_date=target.logical_date,
                run_id=target.run_id,
                schema_version=target.schema_version or "",
                loaded_at=now_iso,
            )
            self._pointer_store.upsert_pointer(pointer)

    def _demote(self, plan: ReconciliationPlan) -> None:
        """Remove warehouse pointers for non-authoritative partitions."""
        for pointer in plan.demote:
            self._pointer_store.delete_pointer(
                pointer.source,
                pointer.customer_id,
                pointer.query_name,
                pointer.logical_date,
            )
