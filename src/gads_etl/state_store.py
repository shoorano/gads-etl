"""SQLite-backed access layer for PartitionState records."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Optional

PartitionStatus = str  # constrained elsewhere (pending|success|failed)


@dataclass
class PartitionState:
    source: str
    customer_id: str
    query_name: str
    logical_date: date
    status: PartitionStatus
    current_run_id: Optional[str]
    schema_version: Optional[str]
    record_count: Optional[int]
    updated_at: datetime
    error_message: Optional[str]
    attempt_count: Optional[int] = None


class PartitionStateRepository:
    """Lightweight DAO for the partition state table."""

    def __init__(self, db_path: str | Path = "data/state_store.db") -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS partition_state (
                    source TEXT NOT NULL,
                    customer_id TEXT NOT NULL,
                    query_name TEXT NOT NULL,
                    logical_date DATE NOT NULL,
                    status TEXT NOT NULL CHECK (status IN ('pending','success','failed')),
                    current_run_id TEXT,
                    schema_version TEXT,
                    record_count BIGINT,
                    updated_at TIMESTAMPTZ NOT NULL,
                    error_message TEXT,
                    attempt_count INTEGER,
                    PRIMARY KEY (source, customer_id, query_name, logical_date)
                )
                """
            )

    def get_partition_state(
        self, source: str, customer_id: str, query_name: str, logical_date: date
    ) -> Optional[PartitionState]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT *
                  FROM partition_state
                 WHERE source=? AND customer_id=? AND query_name=? AND logical_date=?
                """,
                (source, customer_id, query_name, logical_date.isoformat()),
            ).fetchone()
            return self._row_to_state(row)

    def list_partition_states(
        self,
        status: Optional[str] = None,
        customer_id: Optional[str] = None,
        query_name: Optional[str] = None,
        since: Optional[date] = None,
        until: Optional[date] = None,
        limit: Optional[int] = None,
    ) -> list[PartitionState]:
        where_clauses = []
        params: list[str] = []
        if status:
            where_clauses.append("status = ?")
            params.append(status)
        if customer_id:
            where_clauses.append("customer_id = ?")
            params.append(customer_id)
        if query_name:
            where_clauses.append("query_name = ?")
            params.append(query_name)
        if since:
            where_clauses.append("logical_date >= ?")
            params.append(since.isoformat())
        if until:
            where_clauses.append("logical_date <= ?")
            params.append(until.isoformat())

        where_sql = ""
        if where_clauses:
            where_sql = "WHERE " + " AND ".join(where_clauses)

        limit_sql = ""
        if limit is not None:
            limit_sql = f" LIMIT {int(limit)}"

        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT *
                  FROM partition_state
                  {where_sql}
                 ORDER BY updated_at DESC
                 {limit_sql}
                """,
                tuple(params),
            ).fetchall()
            return [self._row_to_state(row) for row in rows if row]

    def upsert_partition_state(self, state: PartitionState) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO partition_state (
                    source,
                    customer_id,
                    query_name,
                    logical_date,
                    status,
                    current_run_id,
                    schema_version,
                    record_count,
                    updated_at,
                    error_message,
                    attempt_count
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source, customer_id, query_name, logical_date) DO UPDATE SET
                    status=excluded.status,
                    current_run_id=excluded.current_run_id,
                    schema_version=excluded.schema_version,
                    record_count=excluded.record_count,
                    updated_at=excluded.updated_at,
                    error_message=excluded.error_message,
                    attempt_count=excluded.attempt_count
                """,
                (
                    state.source,
                    state.customer_id,
                    state.query_name,
                    state.logical_date.isoformat(),
                    state.status,
                    state.current_run_id,
                    state.schema_version,
                    state.record_count,
                    state.updated_at.isoformat(),
                    state.error_message,
                    state.attempt_count,
                ),
            )

    def _row_to_state(self, row: Optional[sqlite3.Row]) -> Optional[PartitionState]:
        if row is None:
            return None
        return PartitionState(
            source=row["source"],
            customer_id=row["customer_id"],
            query_name=row["query_name"],
            logical_date=date.fromisoformat(row["logical_date"]),
            status=row["status"],
            current_run_id=row["current_run_id"],
            schema_version=row["schema_version"],
            record_count=row["record_count"],
            updated_at=datetime.fromisoformat(row["updated_at"]),
            error_message=row["error_message"],
            attempt_count=row["attempt_count"],
        )


__all__ = ["PartitionState", "PartitionStateRepository"]
