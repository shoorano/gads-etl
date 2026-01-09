"""Filesystem-backed RawSink implementation."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from .raw_sink import PartitionKey, PartitionReader, PartitionWriter, RawSink


def _logical_dir(root: Path, key: PartitionKey) -> Path:
    return (
        root
        / key.source
        / f"customer_id={key.customer_id}"
        / f"query_name={key.query_name}"
        / f"logical_date={key.logical_date}"
    )


def _partition_dir(root: Path, key: PartitionKey, run_id: str) -> Path:
    return _logical_dir(root, key) / f"run_id={run_id}"


class LocalFilesystemPartitionWriter(PartitionWriter):
    """Writes raw partitions to the local filesystem."""

    def __init__(self, payload_path: Path, metadata_path: Path) -> None:
        self._payload_path = payload_path
        self._metadata_path = metadata_path
        self._finalized = metadata_path.exists()
        self._payload_path.parent.mkdir(parents=True, exist_ok=True)

    def _ensure_not_finalized(self) -> None:
        if self._finalized:
            raise RuntimeError("Partition already finalized; cannot write.")

    def write_payload_row(self, row: Mapping[str, object]) -> None:
        self._ensure_not_finalized()
        with self._payload_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row))
            handle.write("\n")

    def finalize(self, metadata: Mapping[str, object]) -> None:
        self._ensure_not_finalized()
        with self._metadata_path.open("w", encoding="utf-8") as handle:
            json.dump(metadata, handle, ensure_ascii=False)
        self._finalized = True


class LocalFilesystemPartitionReader(PartitionReader):
    """Reads raw partitions from the local filesystem."""

    def __init__(self, payload_path: Path, metadata_path: Path) -> None:
        self._payload_path = payload_path
        self._metadata_path = metadata_path

    def iter_payload_rows(self) -> Iterable[Mapping[str, object]]:
        with self._payload_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    yield json.loads(line)

    def read_metadata(self) -> Mapping[str, object]:
        with self._metadata_path.open("r", encoding="utf-8") as handle:
            return json.load(handle)


class LocalFilesystemRawSink(RawSink):
    """Raw sink that persists partitions under the canonical directory layout."""

    def __init__(self, root: Path | str = Path("data/raw")) -> None:
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)

    def write_partition(self, partition_key: PartitionKey, run_id: str) -> PartitionWriter:
        directory = _partition_dir(self._root, partition_key, run_id)
        payload_path = directory / "payload.jsonl"
        metadata_path = directory / "metadata.json"
        return LocalFilesystemPartitionWriter(payload_path, metadata_path)

    def open_partition(self, partition_key: PartitionKey, run_id: str) -> PartitionReader:
        directory = _partition_dir(self._root, partition_key, run_id)
        payload_path = directory / "payload.jsonl"
        metadata_path = directory / "metadata.json"
        if not payload_path.exists() or not metadata_path.exists():
            raise FileNotFoundError(f"Partition not found: {directory}")
        return LocalFilesystemPartitionReader(payload_path, metadata_path)

    def list_partitions(self, partition_key: PartitionKey) -> Sequence[str]:
        logical_dir = _logical_dir(self._root, partition_key)
        if not logical_dir.exists():
            return []
        run_ids = []
        for child in logical_dir.iterdir():
            if child.is_dir() and child.name.startswith("run_id="):
                run_ids.append(child.name.replace("run_id=", "", 1))
        run_ids.sort()
        return run_ids


__all__ = [
    "LocalFilesystemRawSink",
]
