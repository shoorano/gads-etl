# Control Plane Specification

## 1. Control Plane vs Data Plane
- **Control Plane responsibilities**: decide *what* logical partitions should be processed (initial runs, retries, backfills), *when* they should be attempted, and update scheduling metadata (pending vs terminal).  
- **Forbidden actions**: control plane must never mutate raw partitions, fabricate run_ids, or mark success/failed directly. It cannot skip the validator or write payload data.  
- **Delegation**: extraction of data and validation/state updates are data-plane actions. Once the control plane marks a partition as pending/retry, the data plane executes the run (extractor + validator) and writes outcomes in state.

## 2. Control Plane Capabilities
- **Requeue logical partitions**: change status from failed (or pending with stale data) to pending, so the data plane will reattempt with a new run_id. This transition is NEVER automatic; only explicit control-plane actions may perform it. Extractors, validators, and consumers are forbidden from toggling failed → pending.
- **Enqueue historical backfills**: insert pending entries for customer/date ranges that never ran or require reprocessing.  
- **Mark partitions terminal**: flag partitions for which retries must stop (max attempts, business rule) by writing metadata (e.g., `error_message`, policy marker) but keeping status=`failed`. “Terminal” is a policy concept; no new status is introduced.
- **Clear terminal flags**: if policy allows, operators can remove the terminal flag to re-enable retries; status stays failed/pending per policy.  
- **Pause/suppress retries**: optionally mark partitions as paused (status remains failed) so automation skips them until unpaused; no raw/state data is altered.

## 3. CLI Command Contracts (Conceptual)

### a. `state retry`
- **Meaning**: transitions selected partitions to `pending`, increments scheduling metadata as needed.  
- **Changes**: status becomes pending, terminal flags cleared (if allowed). `attempt_count` is untouched until the validator runs again.  
- **Must NOT change**: current run_id, raw data, record_count, prior attempt history.  
- **Filters**: customer_id, query_name, logical_date range (since/until). Exact matching only; wildcards disallowed.  
- **Dry-run**: command must support `--dry-run` to list partitions that *would* be requeued without changing state.  
- **Confirmation**: for multi-partition operations, require confirmation or `--force` flag; single partition may skip confirmation.

### b. `state backfill enqueue`
- **Representation**: inserts pending partitions for each logical date in the requested range. If partitions exist, it respects existing status (no overwrite) unless `--force-pending` is provided.  
- **Interaction with daily runs**: backfill partitions are queued alongside daily ones; state differentiates them via timestamps (same schema).  
- **Partial history**: some partitions may stay pending longer; consumers rely on state to detect availability.

### c. `state mark-terminal`
- **Allowed**: only when status is failed and `attempt_count` >= policy thresholds.  
- **Meaning**: adds policy metadata marking the partition as terminal; `status` remains `failed`. Control plane must respect terminal flags and avoid automatic retries.
- **Effect**: automation logs terminal entries for operator review; manual `state retry` is blocked unless `--clear-terminal` used.

### d. `state inspect`
- **Guarantees**: shows actual state rows (not cached), including status, current_run_id, attempt_count, error_message.  
- **Must not hide**: terminal flags, paused status, or zero rows. Missing records must be represented as “no entry found” rather than inferred.

## 4. Batch Semantics
- **Large ranges**: operations may affect thousands of partitions. Commands must iterate deterministically, and partial failures must be reported.  
- **Atomicity**: per-partition atomicity only; batches may partially succeed.  
- **Partial success behavior**: log successes/failures separately, return non-zero exit codes when any partition failed.  
- **Failure modes**: transient DB errors should abort and leave remaining partitions untouched; operators rerun commands after resolving issues.

## 5. Safety Rails
- Confirmation prompts for operations touching more than N partitions (configurable, default e.g., 20).  
- Hard limits on batch size unless `--force` used; large operations demand explicit acknowledgement.  
- Every command must log (stdout/file) which partitions changed. Silent mutations are forbidden.  
- Audit trail: record user, timestamp, command, filters, and whether dry-run or force flags were used.  
- Validation of filters to prevent accidental `retry --since 1900`.

## 6. Automation Interface
- **Execution model**: automation loops (cron, daemon, orchestrator) call the same CLI/API commands described above.  
- **Idempotency**: commands must be idempotent (re-running `state retry` on already pending partitions should no-op).  
- **Reentrancy & crash safety**: automation must tolerate crashes; after restart it re-evaluates state and reissues commands without double-scheduling.  
- **Scheduling**: automation decides timing/backoff using data from PartitionState (attempt_count, updated_at). It does not bypass validator.

## 7. Invariants
- Control plane never writes payload data or metadata inside raw partitions.  
- Only pending partitions are scheduled for extraction; success/failed remain until validator updates them.  
- state retry/backfill enqueue never delete records; they only create or change status.  
- Terminality is policy metadata layered on top of `status=failed`; control plane alone interprets it, and consumers treat terminal partitions as permanently unavailable.  
- All commands respect run_id immutability; `current_run_id` is never changed by control-plane commands.

## 8. Explicit Non-Goals
- No definition of the scheduling engine (cron, Airflow, Dagster).  
- No performance or throughput guarantees.  
- No warehouse/consumer workflows.  
- No UI design.  
- No data retention/purging policy.
