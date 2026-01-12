"""Factory for selecting RawSink backend."""
from __future__ import annotations

import os

from pathlib import Path

from .raw_sink import RawSink
from .raw_sink_local import LocalFilesystemRawSink
from .raw_sink_object import ObjectStorageRawSink, S3Config


def create_raw_sink() -> RawSink:
    backend = os.getenv("RAW_SINK", "filesystem").lower()
    if backend == "filesystem":
        root = os.getenv("RAW_SINK_ROOT", "data/raw")
        return LocalFilesystemRawSink(Path(root))
    if backend == "object":
        bucket = os.getenv("RAW_SINK_BUCKET")
        prefix = os.getenv("RAW_SINK_PREFIX", "raw")
        if not bucket:
            raise RuntimeError("RAW_SINK_BUCKET is required for object storage")
        return ObjectStorageRawSink(
            S3Config(
                bucket=bucket,
                prefix=prefix,
                endpoint_url=os.getenv("RAW_SINK_ENDPOINT_URL"),
                region=os.getenv("RAW_SINK_REGION"),
                access_key=os.getenv("RAW_SINK_ACCESS_KEY_ID"),
                secret_key=os.getenv("RAW_SINK_SECRET_ACCESS_KEY"),
            )
        )
    raise RuntimeError(f"Unsupported RAW_SINK backend: {backend}")
