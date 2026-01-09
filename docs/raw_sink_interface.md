## Raw sink interface specification

### 1. Definitions
- **RawSink** – Backend-agnostic component responsible for persisting immutable raw partitions. Different implementations (local filesystem, object storage, etc.) must expose the same capability surface.
- **PartitionWriter** – Handle returned by the sink when creating a new raw partition. It encapsulates writing payload rows and finalizing metadata for a specific `(partition_key, run_id)`.
- **PartitionReader** – Handle for reading an existing raw partition. It exposes read-only access to both payload data and metadata.

### 2. Partition identity
- **partition_key** = `(source, customer_id, query_name, logical_date)` matching the logical partition definition in `docs/raw_sink_contract.md`.
- **run_id** – ISO 8601 UTC timestamp with milliseconds identifying one pipeline execution attempt. Every partition path is scoped by `(partition_key, run_id)`.
- Sinks do **not** generate `run_id`. The caller (extractor/orchestrator) provides it, ensuring consistency across metadata, state store, and artifacts.

### 3. Required RawSink operations
1. `write_partition(partition_key, run_id) -> PartitionWriter`
   - Allocates a writer for the specified partition attempt. May resume a partial write if the same `(partition_key, run_id)` already exists but is not finalized.
2. `open_partition(partition_key, run_id) -> PartitionReader`
   - Provides read-only access to an existing partition. Fails if the partition does not exist or is incomplete.
3. `list_partitions(partition_key) -> list[run_id]`
   - Enumerates all known `run_id`s for the given logical partition, ordered or filtered as the implementation sees fit. Used by consumers/state store tooling to discover available runs.

### 4. PartitionWriter contract
- Scoped to exactly one `(partition_key, run_id)`; callers must create a new writer for each attempt.
- Exposes:
  - `write_payload_row(row_dict)` (or equivalent streaming call) to append JSON-serializable rows destined for `payload.jsonl`.
  - `finalize(metadata_dict)` to persist `metadata.json` and mark the partition immutable.
- `finalize()` is called once. After finalization, the writer is closed and further writes MUST fail.
- Crash/retry semantics:
  - Partial data may exist if a process crashes before calling `finalize()`.
  - Retrying within the same `run_id` may reopen the writer and complete the partition (implementation-dependent).
  - Reprocessing outside the original attempt MUST generate a new `run_id` and therefore a new partition directory.

### 5. PartitionReader contract
- Read-only handle bound to `(partition_key, run_id)`.
- Provides:
  - Iteration over `payload.jsonl` rows in the order they were written.
  - Access to `metadata.json` as a structured object.
- Readers MUST NOT mutate payload or metadata. Attempts to write through a reader must raise errors.

### 6. Immutability & concurrency guarantees
- After `finalize()` succeeds, the sink guarantees that the partition’s content is immutable (no overwrites, no appends).
- Sinks must allow concurrent writes as long as `(partition_key, run_id)` differs (e.g., different customers/dates or reprocessing with new run_ids).
- Sinks must reject overwrites of already-finalized partitions. Callers bear responsibility for providing unique run_ids and avoiding concurrent misuse.

### 7. Environment switching
- Backend selection is configuration-driven (e.g., YAML/env). No application code may branch on “filesystem vs object storage”.
- Extractors, validators, and consumers interact solely through the RawSink interface. Switching from local filesystem to S3-compatible storage is a config change only.
- This invariance is architectural: any violation (e.g., direct filesystem calls) is considered a bug irrespective of environment.

### 8. Backend examples (conceptual)
- **LocalFilesystemSink** – Implements the interface using directories and files on disk, respecting the canonical path layout from `docs/raw_sink_contract.md`.
- **ObjectStorageSink (S3-compatible)** – Maps partitions to object keys in an object store that follows S3-like semantics (bucket/key addressing, eventual consistency). “S3-compatible” refers to the API shape, not AWS specifically; providers like Hetzner StorageBox or MinIO qualify.
- These are illustrative; additional implementations (e.g., in-memory for tests) are permitted if they honor the same contract.

### 9. Non-goals
- Schema validation, GAQL interpretation, or schema-version management.
- State store interaction (status tracking, run selection, retries).
- Retry/backoff logic or orchestration concerns.
- Deciding which partition is authoritative (`state_store_contract.md` defines that).
