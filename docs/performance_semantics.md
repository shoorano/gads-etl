# Performance Semantics (Stage 13 Spec)

This document defines concurrency, backpressure, and determinism rules for the ETL pipeline. It is a **spec-only** policy document and must not be interpreted as a scheduling or implementation guide.

## 1. Unit of parallelism
### 1.1 Allowed concurrent units
- **Logical partition** `(source, customer_id, query_name, logical_date)` is the primary unit of parallel work.
- Different logical partitions may execute concurrently at every stage (extract, validate, consume, warehouse publish), subject to the ceilings below.
- Different `run_id` attempts for **different logical partitions** may run concurrently.

### 1.2 Forbidden concurrent units
- The same logical partition must **never** be processed concurrently by more than one writer per stage.
  - Extract: at most one writer may emit raw data for a given logical partition per run attempt.
  - Validate: at most one validator may mark a given logical partition per run attempt.
- The same `(logical partition, run_id)` must never be processed concurrently by multiple writers.
- Consumers must not concurrently read and publish the same logical partition as authoritative without using `PartitionState` as the sole source of truth.

## 2. Concurrency ceilings
### 2.1 Global limits
- A global concurrency ceiling **must** be enforced by the orchestrator or operator policy.
- The ceiling applies to total in-flight logical partitions across all customers and queries.
- The ceiling must be configurable; no fixed defaults are mandated by this spec.

### 2.2 Per-customer limits
- A per-customer concurrency ceiling **must** be enforced.
- At most `N` logical partitions for the same `customer_id` may be in-flight across all queries.
- `N` must be configurable and may be set to 1 for strict isolation.

### 2.3 Per-query limits
- A per-query concurrency ceiling **must** be enforced.
- At most `M` logical partitions for the same `query_name` may be in-flight across all customers.
- `M` must be configurable and may be set to 1 for strict isolation.

### 2.4 In-flight partition limits
- The system must cap the number of in-flight logical partitions per stage.
- In-flight counts include partitions that are queued, executing, or awaiting validation.

## 3. Memory & streaming contracts
### 3.1 Must-stream components
- Raw extractors must stream payload rows to the raw sink without accumulating full partitions in memory.
- Validators must stream raw payloads for inspection; full-partition buffering is prohibited.
- Warehouse loaders must stream curated payloads during staging when they are implemented.

### 3.2 May-buffer components
- Lightweight per-partition metadata (counts, schema version, validation results) may be buffered in memory.
- Small bounded batches are permitted if they do not change correctness or ordering.

### 3.3 Prohibited behaviors
- Loading entire logical partitions into memory.
- Re-reading raw payloads to compensate for memory pressure.
- Writing partial data as authoritative without sealing metadata.

## 4. Backpressure semantics
### 4.1 Downstream slowness
- If a downstream stage is slow or unavailable, upstream stages must **block or yield** rather than continue to emit data for the same logical partition.
- Backpressure must propagate **upstream** in the order: consumer/warehouse → validator → extractor.

### 4.2 Blocking vs yielding
- The component that cannot complete its write (raw sink or curated staging) must block or yield until it can safely proceed.
- The component must not degrade correctness by skipping validation or publishing pointers early.

### 4.3 Pressure propagation
- When backpressure is detected, only the affected logical partitions should stall.
- Unrelated logical partitions must remain eligible for execution within concurrency ceilings.

## 5. Failure isolation
- Failures are isolated to the logical partition and run attempt.
- A failure in one logical partition must **not** stall unrelated partitions.
- Retry attempts for a partition must not block other partitions from progressing, except via global or per-customer/query ceilings.
- Failures must never retroactively affect immutable raw partitions or alter authoritative state for other partitions.

## 6. Determinism guarantees
### 6.1 Ordering
- No global ordering guarantees are required across logical partitions.
- Within a logical partition, visibility is governed strictly by `PartitionState` and (for warehouse) pointer publication.

### 6.2 Visibility
- Consumers see data only when `PartitionState.status=success` and (if applicable) the warehouse pointer matches that authority.
- Partitions that are `pending` or `failed` are never visible as authoritative.

### 6.3 Monotonicity
- Once a partition is marked `success`, it remains authoritative until replaced by a new `run_id` or explicitly demoted by validators.
- Replacements are total and atomic at the logical partition level.

## 7. Interaction with retries and backfills
### 7.1 Retries
- Retries create a new `run_id` and therefore a new execution attempt.
- Retry attempts must respect the same concurrency ceilings as first attempts.
- Multiple retries for the same logical partition must not run concurrently.

### 7.2 Backfills
- Backfills are treated as normal logical partitions and are subject to the same ceilings and backpressure rules.
- Backfills must not starve current-day partitions; operators should enforce separate or stricter ceilings as policy.

## 8. Invariants
### 8.1 Must always be true
- Raw partitions remain immutable once sealed with metadata.
- `PartitionState` remains the sole authority for partition visibility.
- A logical partition is processed by at most one writer per stage at a time.
- Pointer publication never occurs without a matching authoritative `PartitionState`.

### 8.2 Must never happen
- Concurrent writers targeting the same `(logical partition, run_id)`.
- Buffering full partitions in memory for extraction or validation.
- Publishing warehouse pointers for `pending` or `failed` partitions.
- Skipping validation due to backpressure.

## 9. Non-goals
- Defining or selecting specific schedulers, executors, or concurrency primitives.
- Optimization of throughput or latency beyond the safety rules above.
- Automatic tuning of concurrency limits.
- Any change to retry, backfill, or authority semantics defined elsewhere.
