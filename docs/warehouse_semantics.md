# Warehouse Semantics (Stage 12 Spec)

Stage 12 defines the control-plane semantics for projecting `PartitionState` into a warehouse. This is a **spec-only** stage: no loaders, database choices, or orchestration changes are permitted until a future implementation stage cites this document.

## Scope and invariants
- Applies to every `(source, customer_id, query_name, logical_date)` logical partition defined in `docs/state_store_contract.md`.
- Raw partitions remain immutable and continue to be sealed by `metadata.json`.
- `PartitionState` stays the sole authority. This spec only describes how a warehouse interprets that authority.
- Preferred semantic is **replace-by-logical-partition**. No lineage, merge, or append strategies are permitted unless another stage supersedes this spec.

## Terminology
- **Warehouse partition** – The unit of truth stored in warehouse tables. It is keyed by the logical partition and materialized from a single authoritative `run_id`.
- **Loading** – Copying the validated raw payload referenced by `PartitionState.current_run_id` into the warehouse partition, replacing any existing rows for that logical partition, and atomically publishing the new version.
- **Active partition** – A logical partition whose `PartitionState.status` is `success`. Only active partitions may be loaded or exposed to consumers.
- **Load record** – Operational metadata (outside the warehouse tables) describing when a partition was last loaded, from which `run_id`, and with which `schema_version`.

## Loading semantics
1. The loader enumerates `PartitionState` rows filtered to `status=success`.
2. For each row, it looks up the immutable raw partition identified by `current_run_id`.
3. The loader materializes the data into warehouse staging storage keyed by `(source, customer_id, query_name, logical_date, run_id)`.
4. Once staging is complete, the loader swaps the warehouse partition pointer for `(source, customer_id, query_name, logical_date)` to the new staging artifact and removes the previous pointer.
5. The loader records a load record containing `loaded_at`, `run_id`, `schema_version`, and `record_count`. The record is idempotent and may be rewritten with the same values.
6. A load is considered complete only after the pointer swap succeeds; partial staging does not change warehouse truth.

Loading never mutates raw partitions, does not invent new logical partitions, and refuses to act on `pending` or `failed` states.

## Unit of idempotency
- The idempotency unit is the logical partition. Multiple load attempts for the same `(source, customer_id, query_name, logical_date)` plus identical `current_run_id` must yield byte-equivalent warehouse results and identical load records.
- Rerunning a load for the same logical partition + run_id is safe and required to tolerate retries, process restarts, or deduplicated work scheduling.
- Because `run_id` fences every extractor attempt, a new `run_id` implies a new warehouse rewrite for that logical partition.

## Mapping PartitionState to warehouse truth
- Warehouse truth is the materialized set `{logical partition → run_id}` where `status=success`.
- The warehouse MUST persist a pointer table (conceptual, implementation-specific) that mirrors `PartitionState` but only after the load completes. Until a load finishes, `PartitionState` may already point at a run_id that warehouse tables do not yet reflect; loaders must reconcile this by checking for mismatches.
- If `PartitionState` contains a logical partition that has never been loaded, the warehouse stores no rows for that partition.
- A warehouse pointer must include `schema_version`. When the pointer differs from `PartitionState` (`run_id` or `schema_version` mismatch), the loader must enqueue a replacement load.

## Replacement semantics when authority changes
- Authority changes when `PartitionState.current_run_id` changes for a logical partition, regardless of whether the previous row was `success`, `pending`, or `failed`.
- Replacement is **total**: the warehouse must delete (or atomically overwrite) every row previously associated with that logical partition before publishing the new data.
- The loader may not co-mingle data from different `run_id`s within the same logical partition. If a replacement fails halfway, the warehouse pointer must remain on the last fully successful run.
- If a validator demotes a partition from `success` to `failed`, the warehouse must mark the logical partition as `unavailable` and remove (or hide) its rows before exposing the failure. No stale data may remain visible.

## Backfill behavior
- Backfill jobs produce the same `PartitionState` rows as daily processing, so warehouse semantics remain identical.
- Load scheduling MAY prioritize newer logical dates, but ordering does not change correctness because each partition is independent.
- Gaps (missing logical dates) stay invisible to consumers until their partitions reach `status=success` and are loaded.
- Large historical runs must still respect replace-by-partition semantics; bulk inserts cannot skip the pointer swap step even if thousands of partitions are loaded in a batch.

## Schema evolution
- `schema_version` in both `metadata.json` and `PartitionState` defines the warehouse schema contract for that logical partition.
- A schema evolution occurs whenever the validator writes a `PartitionState` row whose `schema_version` differs from the previous authoritative version for the same `(source, query_name)`.
- Warehouse tables must be partitioned or versioned such that two schema versions for the same `(source, query_name)` never mix within a single logical partition. Acceptable strategies:
  - Separate physical tables per `(query_name, schema_version)`.
  - A shared table with an explicit `schema_version` discriminator and column superset, provided the loader enforces column-level compatibility.
- When a new schema version appears, every logical partition referencing that version must be fully reloaded using replace-by-partition semantics before consumers can rely on it.
- Schema downgrades (reverting to an older version) are allowed only if the validator issues a new `run_id` whose `schema_version` matches the intended target; the warehouse treats it as another replacement.

## Consumer guarantees
- Consumers query only warehouse partitions whose pointer matches a `PartitionState` row with `status=success`.
- Reads at `(source, customer_id, query_name, logical_date)` see data from exactly one `run_id`; no mixed versions exist.
- Replacement is atomic: consumers never observe partially replaced partitions because pointer swaps are the publish point.
- Consumers can reconstruct freshness by reading the load record metadata (`loaded_at`, `run_id`, `schema_version`).
- Backfills and retries do not reorder existing data; once a partition is reloaded, consumers immediately see the new content with no duplication.

## Acceptance criteria
1. Documentation exists (this file) that defines loading, idempotency, PartitionState mapping, replacement, backfill, schema evolution, and consumer guarantees.
2. Replace-by-logical-partition semantics are the mandated default, including handling for authority changes and validator demotions.
3. Schema evolution is explicitly tied to `schema_version`, and loaders are required to treat differing versions as separate replacement events.
4. Consumers rely solely on the warehouse pointer derived from `PartitionState`, ensuring consistent guarantees independent of physical storage choices.
