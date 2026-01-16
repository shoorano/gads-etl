"""S3-compatible RawSink implementation."""
from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

import boto3
from botocore.client import BaseClient
from botocore.exceptions import ClientError

from .raw_sink import PartitionKey, PartitionReader, PartitionWriter, RawSink


@dataclass
class S3Config:
    bucket: str
    prefix: str
    endpoint_url: str | None = None
    region: str | None = None
    access_key: str | None = None
    secret_key: str | None = None


def _partition_prefix(prefix: str, key: PartitionKey) -> str:
    return "/".join(
        [
            prefix.rstrip("/"),
            key.source,
            f"customer_id={key.customer_id}",
            f"query_name={key.query_name}",
            f"logical_date={key.logical_date}",
        ]
    ).strip("/")


def _object_key(prefix: str, run_id: str, filename: str) -> str:
    return f"{prefix}/run_id={run_id}/{filename}"


class ObjectStorageRawSink(RawSink):
    def __init__(self, config: S3Config) -> None:
        session = boto3.session.Session()
        self.client: BaseClient = session.client(
            "s3",
            endpoint_url=config.endpoint_url,
            region_name=config.region,
            aws_access_key_id=config.access_key,
            aws_secret_access_key=config.secret_key,
        )
        self.bucket = config.bucket
        self.prefix = config.prefix.strip("/")

    def write_partition(self, partition_key: PartitionKey, run_id: str) -> PartitionWriter:
        prefix = _partition_prefix(self.prefix, partition_key)
        payload_key = _object_key(prefix, run_id, "payload.jsonl")
        metadata_key = _object_key(prefix, run_id, "metadata.json")
        if self._object_exists(metadata_key):
            raise RuntimeError("Partition already finalized; metadata exists")
        return S3PartitionWriter(self.client, self.bucket, payload_key, metadata_key)

    def open_partition(self, partition_key: PartitionKey, run_id: str) -> PartitionReader:
        prefix = _partition_prefix(self.prefix, partition_key)
        payload_key = _object_key(prefix, run_id, "payload.jsonl")
        metadata_key = _object_key(prefix, run_id, "metadata.json")
        if not self._object_exists(metadata_key):
            raise FileNotFoundError("Partition metadata missing (not finalized)")
        return S3PartitionReader(self.client, self.bucket, payload_key, metadata_key)

    def list_partitions(self, partition_key: PartitionKey) -> Sequence[str]:
        prefix = _partition_prefix(self.prefix, partition_key)
        logical_prefix = f"{prefix}/"
        paginator = self.client.get_paginator("list_objects_v2")
        run_ids = set()
        for page in paginator.paginate(
            Bucket=self.bucket,
            Prefix=logical_prefix,
            Delimiter="/",
        ):
            for cp in page.get("CommonPrefixes", []) or []:
                part = cp.get("Prefix", "").rstrip("/")
                if part.endswith("metadata.json"):
                    continue
                if "run_id=" in part:
                    run_ids.add(part.split("run_id=", 1)[1])
        return sorted(run_ids)

    def _object_exists(self, key: str) -> bool:
        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
            return True
        except ClientError as exc:  # pragma: no cover - network errors
            if exc.response["Error"].get("Code") in ("404", "NotFound"):
                return False
            raise


class S3PartitionWriter(PartitionWriter):
    def __init__(self, client: BaseClient, bucket: str, payload_key: str, metadata_key: str) -> None:
        self.client = client
        self.bucket = bucket
        self.payload_key = payload_key
        self.metadata_key = metadata_key
        self._tempfile = tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", delete=False)
        self._finalized = False

    def write_payload_row(self, row: Mapping[str, object]) -> None:
        if self._finalized:
            raise RuntimeError("Partition already finalized")
        self._tempfile.write(json.dumps(row))
        self._tempfile.write("\n")

    def finalize(self, metadata: Mapping[str, object]) -> None:
        if self._finalized:
            raise RuntimeError("Partition already finalized")
        self._tempfile.flush()
        os.fsync(self._tempfile.fileno())
        self._tempfile.close()
        try:
            if self._object_exists(self.metadata_key):
                raise RuntimeError("Partition already finalized; metadata exists")
            self.client.upload_file(self._tempfile.name, self.bucket, self.payload_key)
            self.client.put_object(
                Bucket=self.bucket,
                Key=self.metadata_key,
                Body=json.dumps(metadata).encode("utf-8"),
                ContentType="application/json",
            )
            self._finalized = True
        finally:
            os.remove(self._tempfile.name)

    def _object_exists(self, key: str) -> bool:
        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
            return True
        except ClientError as exc:
            if exc.response["Error"].get("Code") in ("404", "NotFound"):
                return False
            raise


class S3PartitionReader(PartitionReader):
    def __init__(self, client: BaseClient, bucket: str, payload_key: str, metadata_key: str) -> None:
        self.client = client
        self.bucket = bucket
        self.payload_key = payload_key
        self.metadata_key = metadata_key

    def iter_payload_rows(self) -> Iterable[Mapping[str, object]]:
        obj = self.client.get_object(Bucket=self.bucket, Key=self.payload_key)
        body = obj["Body"]
        for line in body.iter_lines():
            if line:
                yield json.loads(line.decode("utf-8"))

    def read_metadata(self) -> Mapping[str, object]:
        obj = self.client.get_object(Bucket=self.bucket, Key=self.metadata_key)
        return json.loads(obj["Body"].read().decode("utf-8"))
