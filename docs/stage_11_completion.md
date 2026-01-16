# Stage 11 Completion

Stage 11 (Storage Realism) is considered complete and locked. The following deliverables are in place:

1. **ObjectStorageRawSink** – S3-compatible raw sink implemented with metadata-last sealing and overwrite protection.
2. **MinIO parity tests** – Integration suite (marked `minio`) verifies write/read/list/immutability against MinIO; opt-in for CI parity.
3. **Packaging discipline** – src layout with setuptools configuration, editable install workflow, and unit test guard (`tests/unit/test_imports.py`).
4. **CLI reality** – `gads-etl` console script installs via editable mode; CLI commands are runnable (daily, control-plane, state inspection).
5. **Editable install workflow** – Canonical dev loop is `uv venv`, `source .venv/bin/activate`, `pip install -e .`; no sys.path hacks or uv run shortcuts allowed.
6. **Invariant lock** – No future changes may reintroduce packaging shortcuts, path hacks, or alternative sink semantics without reopening a new stage with a spec.

With these conditions satisfied, Stage 11 is closed. Any storage or packaging changes require a new stage specification.
