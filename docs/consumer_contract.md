# Consumer Contract

## Definition
Consumers are downstream systems (analytics tools, warehouses, dashboards) that read pipeline outputs after they have been validated. Consumers are read-only clients: they never mutate raw data or state.

## Source of truth
The state store (PartitionState) is the sole source of truth for authoritative data. A consumer must consult PartitionState to determine which `(source, customer_id, query_name, logical_date)` partitions are safe (`status=success`) and which run_id is selected.

## Partition discovery
Consumers enumerate logical partitions via the state store (see `docs/diagrams/system_overview.d2`). Filters such as customer, date, query, or status are applied against PartitionState; raw directories are never scanned blindly. Missing state entries imply `pending` work and must not be read.

## Authority rules
- Only partitions marked `status=success` are authoritative.  
- The associated `current_run_id` identifies the exact raw partition directory.  
- Multiple run_ids may exist; consumers must read only the run chosen in state.  
- `pending` or `failed` partitions are off-limits until state transitions to `success`.

## Partial availability
It is normal for some partitions to be `pending` or `failed` while others are `success`. Consumers must tolerate gaps: they either wait for state to advance or explicitly query state to know the latest available logical date per customer/query. There is no guarantee that all customers or dates reach success simultaneously.

## Reprocessing semantics
Reprocessing a logical partition produces a new run_id but leaves prior data intact. The validator updates state to point at the new run_id once it passes validation. Consumers must always follow the `current_run_id`; old run directories remain for auditing but are no longer authoritative.

## Immutability guarantees
Raw partitions (payload.jsonl + metadata.json) are immutable once finalized. Their parent directories include the run_id, ensuring that retries never overwrite prior data. State entries may change (status, run_id) but raw files do not.

## Forbidden behaviors
- Reading raw partitions without consulting state.  
- Consuming `pending` or `failed` partitions.  
- Mutating raw data or metadata.  
- Writing to PartitionState (only validators may write).  
- Assuming synchronized availability across customers or dates.  
- Deleting or modifying historical run directories.

## Example flows
1. **Daily consumer**: Query PartitionState for `status=success`, `logical_date=2024-06-10`. For each row, read the matching raw partition (`run_id` dir) and load it into the warehouse. Skip partitions not marked success.  
2. **Gap detection**: Consumer checks for recent `pending` entries; if any exist beyond their freshness SLA, they alert operators instead of ingesting partial data.  
3. **Reprocessing follow-up**: After an operator reprocesses a failed day, state now points to a new run_id. Consumer re-ingests that logical partition using the updated `current_run_id` and archives or supersedes previous warehouse records accordingly.  
4. **Historical replay**: When building historical dashboards, consumer iterates over state for the customer/date range of interest; only rows present (success) are ingested. Missing rows trigger backlog tracking rather than blind raw reads.  
