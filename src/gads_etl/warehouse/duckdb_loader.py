"""DuckDB-backed warehouse loader honoring docs/warehouse_semantics.md."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Iterable, Mapping

import duckdb

from ..raw_sink import PartitionKey, RawSink
from ..state_store import PartitionState, PartitionStateRepository
from .pointer_store import WarehousePointer, WarehousePointerStore


class DuckDBWarehouseLoader:
    """Physical warehouse loader that replaces data by logical partition."""

    _fixed_columns = ("source", "customer_id", "logical_date", "run_id")

    def __init__(
        self,
        partition_state_repository: PartitionStateRepository,
        pointer_store: WarehousePointerStore,
        raw_sink: RawSink,
        db_path: str = "data/warehouse.duckdb",
    ) -> None:
        self._partition_state_repository = partition_state_repository
        self._pointer_store = pointer_store
        self._raw_sink = raw_sink
        self._db_path = db_path

    def run(self) -> None:
        """Load all authoritative partitions into DuckDB and publish pointers."""
        states = self._partition_state_repository.list_partition_states(
            status="success"
        )
        success_keys = {
            (
                state.source,
                state.customer_id,
                state.query_name,
                state.logical_date.isoformat(),
            )
            for state in states
            if state.current_run_id
        }

        for state in states:
            if not state.current_run_id:
                continue
            pointer = self._pointer_store.get_pointer(
                state.source,
                state.customer_id,
                state.query_name,
                state.logical_date.isoformat(),
            )
            if pointer and pointer.run_id == state.current_run_id:
                if pointer.schema_version == (state.schema_version or ""):
                    continue
            self._load_partition(state)

        for pointer in self._pointer_store.list_pointers():
            key = (
                pointer.source,
                pointer.customer_id,
                pointer.query_name,
                pointer.logical_date,
            )
            if key not in success_keys:
                self._pointer_store.delete_pointer(
                    pointer.source,
                    pointer.customer_id,
                    pointer.query_name,
                    pointer.logical_date,
                )

    def _load_partition(self, state: PartitionState) -> None:
        partition_key = PartitionKey(
            state.source,
            state.customer_id,
            state.query_name,
            state.logical_date.isoformat(),
        )
        run_id = state.current_run_id
        if not run_id:
            return
        reader = self._raw_sink.open_partition(partition_key, run_id)
        metadata = reader.read_metadata()
        metadata_schema_version = metadata.get("schema_version")
        if metadata_schema_version != state.schema_version:
            raise ValueError(
                f"Schema version mismatch for {partition_key}: "
                f"state={state.schema_version} metadata={metadata_schema_version}"
            )

        table_name = self._table_name(state.query_name)
        rows_iter = iter(reader.iter_payload_rows())
        first_row = next(rows_iter, None)

        with duckdb.connect(self._db_path) as conn:
            self._ensure_table(conn, table_name)
            known_keys = set()
            if first_row is not None:
                self._validate_payload_keys(first_row.keys())
                known_keys.update(first_row.keys())
                self._ensure_columns(conn, table_name, known_keys)

            conn.execute("BEGIN")
            try:
                self._delete_partition(conn, table_name, partition_key)
                if first_row is not None:
                    known_keys, insert_sql = self._prepare_insert(
                        conn, table_name, known_keys
                    )
                    self._insert_row(
                        conn,
                        insert_sql,
                        partition_key,
                        run_id,
                        known_keys,
                        first_row,
                    )
                    for row in rows_iter:
                        self._validate_payload_keys(row.keys())
                        new_keys = set(row.keys()) - known_keys
                        if new_keys:
                            self._ensure_columns(conn, table_name, new_keys)
                            known_keys, insert_sql = self._prepare_insert(
                                conn, table_name, known_keys | new_keys
                            )
                        self._insert_row(
                            conn,
                            insert_sql,
                            partition_key,
                            run_id,
                            known_keys,
                            row,
                        )
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise

        pointer = WarehousePointer(
            source=state.source,
            customer_id=state.customer_id,
            query_name=state.query_name,
            logical_date=state.logical_date.isoformat(),
            run_id=run_id,
            schema_version=state.schema_version or "",
            loaded_at=datetime.now(timezone.utc).isoformat(),
        )
        self._pointer_store.upsert_pointer(pointer)

    def _table_name(self, query_name: str) -> str:
        return f"warehouse_{query_name}"

    def _escape_identifier(self, name: str) -> str:
        return name.replace('"', '""')

    def _quoted(self, name: str) -> str:
        return f'"{self._escape_identifier(name)}"'

    def _ensure_table(self, conn: duckdb.DuckDBPyConnection, table_name: str) -> None:
        conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {self._quoted(table_name)} (
                source TEXT NOT NULL,
                customer_id TEXT NOT NULL,
                logical_date DATE NOT NULL,
                run_id TEXT NOT NULL
            )
            """
        )

    def _ensure_columns(
        self,
        conn: duckdb.DuckDBPyConnection,
        table_name: str,
        column_names: Iterable[str],
    ) -> None:
        for name in sorted(column_names):
            conn.execute(
                f"ALTER TABLE {self._quoted(table_name)} "
                f"ADD COLUMN IF NOT EXISTS {self._quoted(name)} TEXT"
            )

    def _prepare_insert(
        self,
        conn: duckdb.DuckDBPyConnection,
        table_name: str,
        keys: set[str],
    ) -> tuple[set[str], str]:
        ordered_keys = sorted(keys)
        columns = list(self._fixed_columns) + ordered_keys
        quoted_columns = ", ".join(self._quoted(col) for col in columns)
        placeholders = ", ".join(["?"] * len(columns))
        sql = (
            f"INSERT INTO {self._quoted(table_name)} "
            f"({quoted_columns}) VALUES ({placeholders})"
        )
        return set(ordered_keys), sql

    def _insert_row(
        self,
        conn: duckdb.DuckDBPyConnection,
        insert_sql: str,
        partition_key: PartitionKey,
        run_id: str,
        keys: set[str],
        row: Mapping[str, object],
    ) -> None:
        ordered_keys = sorted(keys)
        values = [
            partition_key.source,
            partition_key.customer_id,
            partition_key.logical_date,
            run_id,
        ]
        values.extend(self._normalize_value(row.get(key)) for key in ordered_keys)
        conn.execute(insert_sql, values)

    def _normalize_value(self, value: object) -> object:
        if value is None:
            return None
        if isinstance(value, (str, int, float, bool)):
            return value
        return json.dumps(value, separators=(",", ":"))

    def _delete_partition(
        self,
        conn: duckdb.DuckDBPyConnection,
        table_name: str,
        partition_key: PartitionKey,
    ) -> None:
        conn.execute(
            f"DELETE FROM {self._quoted(table_name)} "
            "WHERE source = ? AND customer_id = ? AND logical_date = ?",
            (
                partition_key.source,
                partition_key.customer_id,
                partition_key.logical_date,
            ),
        )

    def _validate_payload_keys(self, keys: Iterable[str]) -> None:
        for key in keys:
            if key in self._fixed_columns:
                raise ValueError(
                    f"Payload key '{key}' conflicts with fixed warehouse columns."
                )
