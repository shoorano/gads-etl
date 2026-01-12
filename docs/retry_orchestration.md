# Retry & Reprocessing Specification

## 1. Definition of retry
- A retry operates on a **logical partition** identified by `(source, customer_id, query_name, logical_date)`.  
- Each retry produces a new `run_id` and corresponding raw partition directory.  
- Individual rows inside a partition are never retried independently; the entire partition is re-extracted and revalidated.  
- The validator remains the only actor that marks a partition as success/failed. Consumers never trigger retries directly.

## 2. State transitions
- `pending → success`: validator accepts a raw partition; `current_run_id` updated to the successful run.  
- `pending → failed`: validator rejects a raw partition; `current_run_id` left unchanged (or `NULL` if none existed).  
- `failed → pending`: NEVER automatic. Only an explicit control-plane action (human or automation) may perform this transition. Extractors, validators, and consumers are FORBIDDEN from triggering it.  
- `failed → failed`: subsequent failed attempts increment `attempt_count` but leave status as failed.  
- `failed → terminal`: terminal is a policy designation, not a new status. Terminal failures are represented as `status=failed` plus control-plane metadata (e.g., attempt_count >= max_attempts, age >= max_age, or explicit marker). Consumers treat terminal failures as permanently unavailable. Validators do not interpret terminality.  
- `success` is terminal unless an operator triggers reprocessing; reprocessing inserts a new attempt that may either succeed (replacing `current_run_id`) or fail (leaving prior success intact).

## 3. Attempt semantics
- `attempt_count` increments on every validator attempt (success or failure).  
- It represents the number of times the validator has tried to assign authority to this logical partition.  
- `attempt_count` never resets; it is monotonically increasing for the lifetime of the partition.  
- A new `run_id` is generated for each attempt; prior runs remain immutable.

## 4. Backoff semantics
- Retry timing is determined externally (control plane).  
- Recommended policy: exponential backoff with caps (e.g., 5 min, 30 min, 2 hr) and jitter.  
- Backoff metadata (next_run_at, backoff_strategy) should be tracked outside PartitionState; PartitionState only records outcomes.  
- The control plane must consult `attempt_count`, `updated_at`, and `error_message` to decide when to reschedule.

## 5. Termination semantics
- Retries stop when:  
  - `status=success` (authoritative run accepted).  
  - `attempt_count` exceeds `max_attempts` (operator-defined).  
  - Logical partition age exceeds `max_age` and policy dictates no further retries.  
- Terminal failure means `status=failed` plus control-plane policy metadata (attempt_count >= max_attempts, age >= max_age, or manual marker). There is no new status enum. Consumers treat terminal partitions as permanently unavailable and validators ignore terminality.

## 6. Backfill interaction
- Historical backfills enqueue many logical partitions as `pending`.  
- Each backfill partition follows the same retry policy: new `run_id` per attempt, `attempt_count` increments, state transitions identical.  
- Partial history: consumers interpret gaps as pending/failed per the consumer contract; they do not assume contiguous success.  
- Operators must ensure backfill retry queues do not starve fresh data by prioritizing scheduling externally.

## 7. Control plane vs data plane
- Control plane (scheduler/orchestrator) decides *which* logical partitions to retry and *when*.  
- Data plane (extractor + validator) executes retries: extractor produces new raw partitions; validator marks success/failed.  
- Consumers and validators are forbidden from self-initiated retries; only the control plane may transition `failed → pending`.

## 8. Operator interface (conceptual)
- Commands:  
  - `state inspect` (already exists) to view status/attempt counts.  
  - Future `state retry --customer-id ... --logical-date ...` to requeue partitions (conceptual).  
  - Audit commands for listing terminal failures.  
- Inspectability: attempt history, error messages, timestamps, and next scheduled retry must be visible.  
- Safety rails:  
  - Require confirmation before resetting large ranges.  
  - Block manual retries if raw sink shows no matching partition.  
  - Log every manual override.

## 9. Invariants
- Raw partitions are immutable; retries never overwrite prior data.  
- State is the sole authority; consumers read only `status=success`.  
- Every attempt increments `attempt_count` exactly once.  
- `current_run_id` always references an existing raw partition.  
- Control plane never schedules two simultaneous retries for the same logical partition with the same run_id.  
- Validators do not mutate raw data or prior attempts.

## 10. Explicit non-goals
- No automatic orchestration implementation here (no cron/Airflow definitions).  
- No consumer-layer retry logic.  
- No performance optimizations or throughput targets.  
- No warehouse or downstream transformations.  
- No policy for data retention/pruning of old runs.
