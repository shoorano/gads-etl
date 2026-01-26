"""Warehouse pointer interfaces enforced by docs/warehouse_semantics.md."""

from dataclasses import dataclass
import sqlite3
from typing import Optional


@dataclass(frozen=True)
class WarehousePointer:
    """Represents a warehouse truth pointer defined in docs/warehouse_semantics.md."""

    source: str
    customer_id: str
    query_name: str
    logical_date: str  # YYYY-MM-DD
    run_id: str
    schema_version: str
    loaded_at: str  # ISO-8601 timestamp


class WarehousePointerStore:
    """Abstract persistence layer for warehouse pointers."""

    def get_pointer(self, source, customer_id, query_name, logical_date):
        """Fetch a pointer for the logical partition."""
        raise NotImplementedError

    def upsert_pointer(self, pointer: WarehousePointer):
        """Insert or replace a pointer."""
        raise NotImplementedError

    def delete_pointer(self, source, customer_id, query_name, logical_date):
        """Remove a pointer for the logical partition."""
        raise NotImplementedError

    def list_pointers(self):
        """Return all warehouse pointers."""
        raise NotImplementedError


class SQLiteWarehousePointerStore(WarehousePointerStore):
    """SQLite-backed WarehousePointerStore respecting docs/warehouse_semantics.md."""

    def __init__(self, db_path: str):
        self._db_path = db_path
        self._conn = sqlite3.connect(self._db_path)
        self._conn.row_factory = sqlite3.Row
        self.ensure_schema()

    def ensure_schema(self):
        """Create the warehouse pointer table if it does not exist."""
        with self._conn:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS warehouse_pointers (
                    source TEXT NOT NULL,
                    customer_id TEXT NOT NULL,
                    query_name TEXT NOT NULL,
                    logical_date DATE NOT NULL,
                    run_id TEXT NOT NULL,
                    schema_version TEXT NOT NULL,
                    loaded_at TIMESTAMPTZ NOT NULL,
                    PRIMARY KEY (source, customer_id, query_name, logical_date)
                )
                """
            )

    def get_pointer(
        self,
        source: str,
        customer_id: str,
        query_name: str,
        logical_date: str,
    ) -> Optional[WarehousePointer]:
        """Fetch a pointer for the logical partition."""
        cursor = self._conn.execute(
            """
            SELECT
                source,
                customer_id,
                query_name,
                logical_date,
                run_id,
                schema_version,
                loaded_at
            FROM warehouse_pointers
            WHERE source = ?
              AND customer_id = ?
              AND query_name = ?
              AND logical_date = ?
            """,
            (source, customer_id, query_name, logical_date),
        )
        row = cursor.fetchone()
        if not row:
            return None
        return WarehousePointer(
            source=row["source"],
            customer_id=row["customer_id"],
            query_name=row["query_name"],
            logical_date=row["logical_date"],
            run_id=row["run_id"],
            schema_version=row["schema_version"],
            loaded_at=row["loaded_at"],
        )

    def upsert_pointer(self, pointer: WarehousePointer):
        """Insert or replace a pointer."""
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO warehouse_pointers (
                    source,
                    customer_id,
                    query_name,
                    logical_date,
                    run_id,
                    schema_version,
                    loaded_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source, customer_id, query_name, logical_date)
                DO UPDATE SET
                    run_id = excluded.run_id,
                    schema_version = excluded.schema_version,
                    loaded_at = excluded.loaded_at
                """,
                (
                    pointer.source,
                    pointer.customer_id,
                    pointer.query_name,
                    pointer.logical_date,
                    pointer.run_id,
                    pointer.schema_version,
                    pointer.loaded_at,
                ),
            )

    def delete_pointer(
        self,
        source: str,
        customer_id: str,
        query_name: str,
        logical_date: str,
    ):
        """Remove a pointer for the logical partition."""
        with self._conn:
            self._conn.execute(
                """
                DELETE FROM warehouse_pointers
                WHERE source = ?
                  AND customer_id = ?
                  AND query_name = ?
                  AND logical_date = ?
                """,
                (source, customer_id, query_name, logical_date),
            )

    def list_pointers(self):
        """Return all warehouse pointers."""
        cursor = self._conn.execute(
            """
            SELECT
                source,
                customer_id,
                query_name,
                logical_date,
                run_id,
                schema_version,
                loaded_at
            FROM warehouse_pointers
            """
        )
        rows = cursor.fetchall()
        return [
            WarehousePointer(
                source=row["source"],
                customer_id=row["customer_id"],
                query_name=row["query_name"],
                logical_date=row["logical_date"],
                run_id=row["run_id"],
                schema_version=row["schema_version"],
                loaded_at=row["loaded_at"],
            )
            for row in rows
        ]
