## Raw sink contract

### 1. Definitions
- **Raw sink**: a durable storage backend (local filesystem, MinIO, S3, etc.) that stores the unmodified payloads received from Google Ads. The sink is the first point of persistence and must retain data for replay, auditing, and downstream consumption.
- **Raw partition**: the minimal immutable unit of storage within the raw sink. Each partition corresponds to one extractor run operating on a single `(source, customer_id, query_name, logical_date, run_id)` combination.

### 2. Partition dimensions (required)
Every partition MUST be uniquely identified by the following dimensions:
1. `source` – name of the upstream system (current value: `google_ads`).
2. `customer_id` – Google Ads customer ID as a string (no hyphens).
3. `query_name` – GAQL query identifier from `config/google_apis.yaml`.
4. `logical_date` – ISO-8601 date (`YYYY-MM-DD`) representing the data slice being extracted.
5. `run_id` – ISO 8601 UTC timestamp with milliseconds (e.g., `2024-06-01T12:34:56.789Z`). A single `run_id` is generated per pipeline execution attempt and is reused for all partitions produced by that attempt. Reprocessing or retrying generates a new `run_id` even if the date range overlaps previous partitions.

### 3. Canonical path layout
Extractors MUST publish partitions under the following logical path template (backend-specific path syntax may vary, but the hierarchy is required):
```
<root>/<source>/customer_id=<customer_id>/query_name=<query_name>/logical_date=<YYYY-MM-DD>/run_id=<run_id>/
```

**Example** (local filesystem):
```
data/raw/google_ads/customer_id=1234567890/query_name=campaign_daily/logical_date=2024-06-01/run_id=2024-06-02T04:05:06.789Z/
    payload.jsonl
    metadata.json
```

### 4. Required partition files
Each partition directory MUST contain exactly:
- `payload.jsonl` – newline-delimited JSON records in the order received from the API. Fields mirror GAQL outputs serialized as snake_case keys (e.g., `campaign_name`).
- `metadata.json` – JSON metadata describing the extraction context and schema version (see below). Additional files may be added in the future but must not replace these two artefacts.

### 5. Metadata fields
`metadata.json` MUST include at least:
- `source` (string)
- `customer_id` (string)
- `query_name` (string)
- `logical_date` (string, `YYYY-MM-DD`)
- `run_id` (string, ISO 8601 UTC with milliseconds)
- `extracted_at` (string, UTC timestamp when the partition was written)
- `schema_version` (string, starts at `"v1"` and only changes when row shape/semantics change)
- `record_count` (integer)
- `api_version` (string, e.g., `v16`)
- `query_hash` or `query_signature` (string, stable representation of the GAQL query as executed)

Additional metadata (e.g., orchestrator identifiers) may be appended but must not contradict these fields.

### 6. Immutability rules
- Raw partitions are immutable in meaning: once `payload.jsonl` and `metadata.json` exist for a given `(source, customer_id, query_name, logical_date, run_id)`, they MUST NOT be modified or overwritten.
- Reprocessing the same logical date MUST create a new `run_id` and therefore a new partition directory. Deleting partitions is a manual, audited operation outside the extractor’s responsibility.

### 7. Retry, reprocessing, and parallel runs
- Retries within the same pipeline attempt reuse the original `run_id` and may create or replace files only if the partition directory was partially written in that attempt (e.g., due to crash). Once the run succeeds, the partition is immutable.
- Reprocessing (intentional rerun of historical dates) MUST generate a new `run_id` even if the GAQL input is identical. Downstream consumers choose which partition to honor (latest wins or state-store guided).
- Parallel runs (concurrent `run_id`s) are permitted as long as they fence by `run_id` (unique directories). No two runs should attempt to write to the same partition path simultaneously.

### 8. Relationship to downstream consumers
- Loaders and state-store components read from raw partitions; they do NOT mutate or delete them.
- The state store references partitions by `(source, customer_id, query_name, logical_date, run_id)` to track processing state, retries, and version selection.
- If a downstream consumer requires deduplication, it must rely on metadata (e.g., newest `run_id`, schema version) rather than mutating the raw sink.

### 9. Schema versioning policy
- `schema_version` starts at `"v1"` and increments only when the payload structure or semantic meaning changes (e.g., new columns with default values, breaking field renames).
- External API changes (GAQL additions/removals) do NOT automatically bump `schema_version`. Maintainers decide whether a change affects row semantics.
- Hard API breaks (missing fields, GAQL errors) MUST fail the extractor run; soft changes (additional fields, new metrics) require human review before deciding to bump the schema version.

### 10. Non-goals
- Automating schema-version bumps or run_id assignment is out of scope for this contract; execution tooling handles those concerns.
- The contract does not define warehouse consumers (loaders), state store implementations, or downstream reconciliation logic.
- No guarantees are made about compression, encryption, or retention policies; those are deployment decisions layered on top of this contract.
