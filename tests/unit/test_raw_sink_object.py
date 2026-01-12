from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

from botocore.exceptions import ClientError

import pytest

from gads_etl.raw_sink_object import (
    ObjectStorageRawSink,
    S3Config,
    S3PartitionWriter,
    _partition_prefix,
    _object_key,
)
from gads_etl.raw_sink import PartitionKey


def test_partition_prefix_mapping():
    key = PartitionKey("google_ads", "123", "campaign", "2024-06-01")
    prefix = _partition_prefix("root", key)
    assert (
        prefix
        == "root/google_ads/customer_id=123/query_name=campaign/logical_date=2024-06-01"
    )
    assert _object_key(prefix, "run", "payload.jsonl").endswith(
        "run_id=run/payload.jsonl"
    )


def _not_found_error():
    return ClientError({"Error": {"Code": "404"}}, "head_object")


def test_writer_finalizes_payload_before_metadata(tmp_path: Path):
    client = MagicMock()
    client.head_object.side_effect = _not_found_error()
    writer = S3PartitionWriter(client, "bucket", "payload", "metadata")
    writer._tempfile.close()
    writer._tempfile = open(tmp_path / "payload.tmp", "w", encoding="utf-8")
    writer.write_payload_row({"a": 1})
    writer.finalize({"b": 2})
    assert client.upload_file.called
    assert client.put_object.called
    upload_args = client.upload_file.call_args[0]
    assert upload_args[1:] == ("bucket", "payload")
    put_kwargs = client.put_object.call_args.kwargs
    assert put_kwargs["Key"] == "metadata"
    assert json.loads(put_kwargs["Body"].decode("utf-8")) == {"b": 2}
