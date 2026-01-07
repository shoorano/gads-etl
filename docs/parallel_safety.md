## Parallel safety policy

### 1. Definition
Parallel safety means the pipeline preserves correctness under retries, partial failures, and concurrent executions. A parallel-safe system never produces ambiguous raw partitions, never exposes consumers to unvetted data, and never corrupts state regardless of how many workers run simultaneously. This is a correctness guarantee, not a performance optimization.

### 2. Current risks (as-is)
- Raw files are written to fixed paths without run fencing (`data/raw/<query>/<date>/payload.jsonl`), so parallel runs overwrite each other.
- Extractors and consumers share the same notion of “latest” without an authority layer; there is no state store in use.
- Retries re-use the same output path, meaning partial failures can invalidate successful data.

### 3. Required safety invariants
1. **Run fencing** – Every write must be scoped to a unique `(partition_key, run_id)` so concurrent attempts cannot clobber each other.
2. **Partition immutability** – Once a partition is finalized, it must never change. Reprocessing produces a new run_id instead of rewriting the same path.
3. **Authority separation** – Raw data and state are decoupled: the raw sink stores all attempts, while the state store dictates which run_id is authoritative.
4. **Retry isolation** – Failures do not invalidate other partitions. Retrying a partition operates independently and picks a new run_id, leaving successful partitions untouched.

### 4. Contract mapping
- **Raw sink contract** enforces run fencing and partition immutability by requiring per-run directories and immutable payload/metadata once finalized.
- **State store contract** provides authority separation and retry isolation: it records which run_id is trusted for each logical partition and never requires overwriting raw data.
- **Raw sink interface** provides the capability surface (`write_partition`, `open_partition`, `list_partitions`) needed to fence writes and read immutable artifacts without backend-specific logic.

### 5. Required changes (conceptual)
1. Replace ad-hoc filesystem writers with the RawSink interface so all writes are run-scoped and backend-agnostic.
2. Centralize run_id generation in the pipeline runner/orchestrator to ensure every attempt has a unique identifier applied consistently across sink, metadata, and state.
3. Move success/failure semantics to loaders/validators that interact with the state store instead of relying on extractor-side heuristics.
4. Drive retries and reprocessing based on the state store (which partitions are pending/failed) rather than re-running entire date ranges blindly.

### 6. Ordering of changes
1. **Introduce RawSink abstraction** (code-level plumbing) and adopt it in extractors so raw writes are fenced by `(partition_key, run_id)`.
2. **Adopt immutable partition layout** per `docs/raw_sink_contract.md`, ensuring run directories are unique and finalization writes metadata.
3. **Implement the state store contract** for loaders/validators, recording `status` and `current_run_id` for each partition.
4. **Wire pipeline flow through state**: extractors produce raw partitions; loaders reference state to mark success/failure; retries query state for pending/failed partitions.

Parallelism must not be enabled before this sequence completes. Running multiple workers without run fencing or a state store risks overwriting partitions and exposing consumers to incorrect data.

### 7. Non-goals
- Performance tuning or throughput improvements.
- Introducing concurrency primitives (threads, async, pools).
- Defining scheduling/orchestration logic.
- Implementation details of sinks, state stores, or loaders beyond the invariants above.
