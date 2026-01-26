"""Curated (warehouse staging) sink abstractions per docs/warehouse_semantics.md."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Mapping

from ..raw_sink import PartitionKey


class CuratedSink:
    """Interface for writing curated (staging) partitions."""

    def stage_partition(
        self,
        partition_key: PartitionKey,
        run_id: str,
        rows: Iterable[Mapping[str, object]],
        schema_version: str,
        record_count: int,
        loaded_at: str,
    ) -> None:
        """Write curated data for a logical partition."""
        raise NotImplementedError


class FilesystemCuratedSink(CuratedSink):
    """Filesystem-backed curated sink using staged directories."""

    def __init__(self, root: str | Path):
        self._root = Path(root)
        self._curated_root = self._root / "curated"
        self._curated_root.mkdir(parents=True, exist_ok=True)

    def stage_partition(
        self,
        partition_key: PartitionKey,
        run_id: str,
        rows: Iterable[Mapping[str, object]],
        schema_version: str,
        record_count: int,
        loaded_at: str,
    ) -> None:
        """Write payload rows and finalize metadata atomically (metadata last)."""
        run_dir = self._partition_run_dir(partition_key, run_id)
        metadata_path = run_dir / "metadata.json"
        if metadata_path.exists():
            raise FileExistsError(f"Curated partition already finalized: {metadata_path}")

        run_dir.mkdir(parents=True, exist_ok=True)
        data_path = run_dir / "data.jsonl"
        self._write_data(data_path, rows)

        metadata = {
            "source": partition_key.source,
            "customer_id": partition_key.customer_id,
            "query_name": partition_key.query_name,
            "logical_date": partition_key.logical_date,
            "run_id": run_id,
            "schema_version": schema_version,
            "record_count": record_count,
            "loaded_at": loaded_at,
        }
        self._write_metadata(metadata_path, metadata)

    def _partition_run_dir(self, partition_key: PartitionKey, run_id: str) -> Path:
        return (
            self._curated_root
            / f"source={partition_key.source}"
            / f"customer_id={partition_key.customer_id}"
            / f"query_name={partition_key.query_name}"
            / f"logical_date={partition_key.logical_date}"
            / f"run_id={run_id}"
        )

    def _write_data(
        self, data_path: Path, rows: Iterable[Mapping[str, object]]
    ) -> None:
        with data_path.open("w", encoding="utf-8") as fp:
            for row in rows:
                fp.write(json.dumps(row, separators=(",", ":")))
                fp.write("\n")

    def _write_metadata(self, metadata_path: Path, metadata: Mapping[str, object]) -> None:
        with metadata_path.open("w", encoding="utf-8") as fp:
            json.dump(metadata, fp, separators=(",", ":"))
            fp.write("\n")
