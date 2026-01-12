# Retry Daemon Specification

## Overview
The retry daemon is a control-plane automation loop that monitors PartitionState for failed partitions and issues explicit `state retry` commands when backoff policy allows. It never writes raw data, fabricates run_ids, or marks success/failed; all authority assignments remain with the validator.

## Responsibilities
- Enumerate failed partitions and evaluate retry eligibility.
- Respect terminal partitions (policy markers) by skipping them unless manually cleared.
- Enforce backoff policy (attempt_count-aware).
- Issue the exact same state transition as `gads-etl state retry`.
- Guarantee idempotency and crash safety.

## Backoff Policy
- Base delay: 5 minutes.
- Multiplier: exponential (delay = base * 2^(attempt_count-1)).
- Cap: 6 hours.
- Jitter: optional ±30 seconds to avoid thundering herd.
- Eligibility condition: `now - updated_at >= delay_for(attempt_count)`.

## Selection Logic
1. Query PartitionState for `status=failed`.
2. Exclude partitions where error_message contains `[terminal]`.
3. For each remaining partition, compute delay as above.
4. If eligible, queue the partition for retry.

## Automation Flow
1. Sleep interval (e.g., 60 seconds).
2. Fetch failed partitions.
3. For eligible partitions, call control-plane retry logic (same code path as CLI). This requires invoking the existing retry function or CLI command programmatically.
4. Log each action (timestamp, partition key, attempt_count, delay).

## Crash Safety & Idempotency
- The daemon keeps no mutable in-memory state; decisions depend solely on PartitionState.
- If the daemon crashes mid-loop, the next iteration re-evaluates state and repeats the same logic; no double scheduling occurs because the retry command is idempotent when status is already pending.
- Concurrency: multiple daemon instances may run concurrently; they will call the same retry command, which ensures only failed partitions transition to pending once.

## Implementation Notes
- Reuse the existing retry command by invoking the same function (`state_retry`) with `dry_run=False`, `force=True`, and appropriate filters.
- Batch retries per customer/query to reduce command invocations.
- Respect safety rails: log actions, allow dry-run runs for testing.

## Explicit Non-Goals
- No custom scheduler beyond the daemon loop.
- No direct manipulation of run_ids, attempt_count, or raw data.
- No new schema fields or metadata.
- No auto-clear of terminal flags.
