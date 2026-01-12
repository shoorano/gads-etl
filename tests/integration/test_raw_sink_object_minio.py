from __future__ import annotations

import os
import uuid

import pytest

from gads_etl.raw_sink import PartitionKey
from gads_etl.raw_sink_object import ObjectStorageRawSink, S3Config

pytestmark = [pytest.mark.integration, pytest.mark.minio]


def _minio_config() -> S3Config:
    endpoint = os.getenv("MINIO_ENDPOINT_URL")
    bucket = os.getenv("MINIO_BUCKET")
    access = os.getenv("MINIO_ACCESS_KEY_ID")
    secret = os.getenv("MINIO_SECRET_ACCESS_KEY")
    prefix = os.getenv("MINIO_PREFIX", "raw-tests")
    if not all([endpoint, bucket, access, secret]):
        pytest.skip("MinIO env vars not configured")
    return S3Config(
        bucket=bucket,
        prefix=prefix,
        endpoint_url=endpoint,
        access_key=access,
        secret_key=secret,
    )


def _ensure_bucket(client, bucket: str) -> None:
    try:
        client.head_bucket(Bucket=bucket)
    except client.exceptions.NoSuchBucket:
        client.create_bucket(Bucket=bucket)


def test_minio_sink_round_trip():
    config = _minio_config()
    sink = ObjectStorageRawSink(config)
    try:
        sink.client.head_bucket(Bucket=config.bucket)
    except Exception:
        sink.client.create_bucket(Bucket=config.bucket)
    run_id = uuid.uuid4().hex
    key = PartitionKey("google_ads", "cust", "campaign", "2024-06-01")
    writer = sink.write_partition(key, run_id)
    writer.write_payload_row({"foo": "bar"})
    writer.finalize({"meta": "data"})

    reader = sink.open_partition(key, run_id)
    rows = list(reader.iter_payload_rows())
    assert rows == [{"foo": "bar"}]
    assert reader.read_metadata() == {"meta": "data"}

    run_ids = sink.list_partitions(key)
    assert run_id in run_ids

    with pytest.raises(RuntimeError):
        writer = sink.write_partition(key, run_id)
        writer.write_payload_row({"foo": "bar"})
        writer.finalize({"meta": "data"})
