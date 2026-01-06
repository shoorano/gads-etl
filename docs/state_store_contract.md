## State store contract

### 1. Definition & purpose
The state store is the authoritative ledger that tracks processing outcomes for logical partitions of raw data. It coordinates between extractors (which emit immutable raw partitions) and downstream consumers (loaders, validators, analytics jobs) by recording which partitions are pending, successful, or failed. The state store is durable, mutable, and independent of any particular storage backend.

### 2. State record definition
Each state record represents exactly one logical partition identified by the tuple `(source, customer_id, query_name, logical_date)`. A record stores metadata such as status, the selected `run_id`, timestamps, and diagnostic details. Multiple `run_id`s may exist for a logical partition, but the state store records which run is currently authoritative.

### 3. Implicit (lazy) creation semantics
State is implicit: a partition with no record is treated as `pending`. Records are created only when a component (loader, validator, operator tooling) observes or queries the partition. This keeps the ledger sparse—only touched partitions appear.

### 4. Status model (v1)
- `pending`: the logical partition exists or is expected but no successful load has been recorded yet. This is the default for missing records.
- `success`: a downstream consumer has validated and accepted the raw partition using the recorded `run_id`.
- `failed`: a downstream consumer attempted to process the partition and determined it is unsafe (e.g., corrupt raw payload, business rule violation).

Statuses apply to logical partitions, not to pipeline executions. A single `run_id` may be used for multiple partitions, and a partition may transition between statuses as new runs are evaluated.

### 5. Relationship between runs, partitions, and state
- Extractors emit raw partitions organized by `(source, customer_id, query_name, logical_date, run_id)` (see `docs/raw_sink_contract.md`).
- The state store references those partitions via `(source, customer_id, query_name, logical_date)` and tracks which `run_id` is authoritative for downstream consumption.
- Multiple run attempts (multiple `run_id`s) for the same logical partition do not overwrite raw data; the state store is responsible for choosing the correct `run_id` (e.g., latest success).

### 6. Retry & reprocessing semantics
- When a loader reprocesses a logical partition, it may update the state record with a new `run_id` if the new partition supersedes the previous one.
- A failed status indicates that no run is safe to consume; retries (new run_ids) must be ingested and validated before updating the status back to `success`.
- Reprocessing does not delete historical raw partitions. The state store merely points to the chosen `run_id` that downstream readers should trust.

### 7. Backfill & new-customer behavior
- For new customers or historical backfills, many logical partitions will start as implicit `pending`. As loaders work through these partitions, they create records and transition them to `success` or `failed`.
- The absence of state entries for future dates is expected. Scheduling systems infer work by enumerating logical partitions and checking for missing records.

### 8. Read-side contract
- Consumers must consult the state store before reading raw partitions. Only partitions with `success` status may be treated as authoritative.
- Consumers may apply their own filtering logic (e.g., newest `run_id`, freshness thresholds) but must not assume raw partitions are valid without a corresponding `success` state.

### 9. Write-side contract
- Only loaders, validators, or explicitly authorized tooling may write to the state store. Extractors never mutate state.
- Writers update existing records or create them lazily when processing a partition. They must:
  - Set `status` to `pending` when claiming work (optional, implementation-dependent).
  - Set `status` to `success` when a partition is fully processed and safe.
  - Set `status` to `failed` when processing detects irrecoverable issues.
  - Record the `run_id` that was examined along with timestamps and diagnostic metadata.
- Writers must not delete records except through audited maintenance procedures.

### 10. Non-goals
- The contract does not prescribe the storage technology (SQL, NoSQL, object store) or schema implementation.
- It does not define orchestration workflows, retry policies, or SLA monitoring; those layers consume the state store but are separate concerns.
- The state store does not replace raw storage, warehouse sinks, or metrics systems; it only records logical partition outcomes.
