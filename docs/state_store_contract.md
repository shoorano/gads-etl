## State store contract

### 1. Definitions
- **State store** – A durable coordination ledger that records the processing status of each logical partition of Google Ads data. It is separate from raw sinks and warehouse consumers (warehouse loaders) and exists solely to answer “is this partition safe to consume?”.
- **State record (`PartitionState`)** – A single row describing the status of one logical partition plus the metadata required to identify which raw partition (`run_id`) is authoritative.
- **Logical partition key** – The tuple `(source, customer_id, query_name, logical_date)` describing the smallest independent slice of work for this pipeline.

### 2. Logical partition key
- Fields:
  1. `source` – e.g., `google_ads` (allows future multi-source expansion).
  2. `customer_id` – canonical Ads customer identifier (string, no hyphens).
  3. `query_name` – GAQL query identifier from `config/google_apis.yaml`.
  4. `logical_date` – UTC date (`YYYY-MM-DD`) representing the reporting day.
- The key mirrors the partition layout defined in `docs/raw_sink_contract.md`. State is implicit: if no row exists for a key, it is treated as `pending` and the system assumes work still needs to be validated.

### 3. Status model
- `pending` – No trustworthy data exists yet for the partition. This includes keys with no row (implicit pending) or records explicitly set to pending.
- `success` – The validator has inspected a raw partition and declared the referenced `run_id` safe for downstream consumption.
- `failed` – The validator inspected a raw partition and found it invalid (bad payload, schema mismatch, business rule violation). Consumers must not read failed partitions.

`failed` indicates that at least one run attempt was executed and rejected. Logical partitions with no attempts and no state row remain implicitly `pending`.

Statuses are about consumer safety, not extractor progress. They attach to logical partitions, not to run attempts.

### 4. Authoritative selection (“what wins”)
- Each state record contains `current_run_id`, pointing to the raw partition (see `docs/raw_sink_contract.md`) that should be consumed.
- Retries and reprocessing create new run directories (`run_id`s). The state store chooses which run is authoritative by updating `current_run_id` when a newer run supersedes an older one.
- Multiple `run_id`s may exist for the same logical partition; only the one referenced by the state record is considered trusted.

### 5. State lifecycle (write-side)
1. **Creation (lazy)** – No row exists until a validator touches the partition. Missing rows imply `pending`.
2. **Writers** – Only validators (and tightly-scoped operational tooling) insert or update state. Extractors never write state.
3. **Transitions**:
   - When processing starts, the writer may insert a record (optional) or simply continue with implicit pending.
   - On success, writers must upsert a record with `status=success`, `current_run_id` referencing the validated raw partition, and metadata such as `schema_version`, `record_count`, `updated_at`.
   - On failure, writers upsert `status=failed`, capture the `run_id` examined, and populate `error_message`. Future retries update the same row once a new run is validated.
   - Writers are not required to insert an explicit `pending` row. Absence of a state record is semantically equivalent to `pending`.

### 6. Consumer contract (read-side)
- Consumers MUST query the state store before reading raw data.
- Only partitions with `status=success` are safe to ingest. Missing rows or `pending` status indicate incomplete work; consumers must wait or trigger validators to reprocess the partition.
- For backfills or new customers, large date ranges will appear as implicit `pending`. Consumers should treat missing rows as “not ready” even if raw files exist.
- When a partition is reprocessed, consumers rely on `current_run_id` to know which raw directory to read; past run_ids remain immutable but may be obsolete.

### 7. Minimal schema (v1)
```
PartitionState(
    source TEXT,
    customer_id TEXT,
    query_name TEXT,
    logical_date DATE,
    status TEXT CHECK (status IN ('pending','success','failed')),
    current_run_id TEXT,
    schema_version TEXT,
    record_count BIGINT,
    updated_at TIMESTAMP WITH TIME ZONE,
    error_message TEXT,
    attempt_count INTEGER DEFAULT 0,
    PRIMARY KEY (source, customer_id, query_name, logical_date)
)
```
- `current_run_id` references the chosen raw partition (`run_id`).
- `schema_version` mirrors the version written in `metadata.json` for the raw partition.
- `record_count` is the number of rows ingested from the authoritative run.
- `error_message` captures failure context; empty/null for success.
- `attempt_count` (optional) can track how many run_ids were evaluated.

### 8. Examples
1. **New customer signup** – The orchestrator schedules dates for the new customer. Initially, the state store has no rows for those keys → implicit `pending`. Once validators review each day, they insert rows with `status=success`.
2. **Partial success across customers** – Customer A’s partitions reach `success`, while Customer B’s remain `pending` because validators haven’t processed them yet. Consumers reading customer B’s data must wait despite raw files existing, because state is not `success`.
3. **Retry failed partitions** – Suppose `2024-06-01` for customer A failed due to schema mismatch. The state row shows `status=failed`, `current_run_id` pointing to the problematic run, and an error message. After fixing the issue and reprocessing, the validator updates `current_run_id` to the new run and sets `status=success`.
4. **Reprocessing updates run_id** – When backfilling `2024-05-15`, the validator chooses a new `run_id`. The state row (which previously referenced the old run) is updated to point to the new run_id and timestamp. Raw data from the old run remains in storage but is no longer authoritative.

### 9. Non-goals
- The state store is not a data sink; it does not store raw payloads or aggregates.
- It does not auto-bump schema versions or interpret GAQL changes; operators must update `schema_version` deliberately.
- It does not enforce orchestration policies (scheduling, retries). Those systems use the state store but are specified elsewhere.
