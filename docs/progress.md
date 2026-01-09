# Pipeline Architecture Progress

## Foundations

- [x] Stage 1 — Raw partition contract  
  - Summary: Documented canonical partition layout, metadata fields, and immutability guarantees.  
  - Key decisions: run_id fencing, schema_version rules, immutable payload/metadata pair.  
  - Locked invariants: raw partitions never overwritten, reprocessing always new run_id, metadata fields enforced.

- [x] Stage 2 — State semantics & authority model  
  - Summary: Defined lazy PartitionState ledger and tri-state status.  
  - Key decisions: status scoped to logical partition, missing row = pending, loader/validator is sole writer.  
  - Locked invariants: consumers trust state only, Extractor never touches state.

- [x] Stage 3 — Raw sink abstraction  
  - Summary: Introduced RunContext, RawSink interface, and lifecycle (writer, reader, finalize).  
  - Key decisions: backend-agnostic sink interface, per-run writers, no sink-driven logic.  
  - Locked invariants: sinks immutable, configuration selects backend.

- [x] Stage 4 — Parallel-safety rules  
  - Summary: Formalized run fencing, retry isolation, authority separation before enabling parallel runs.  
  - Key decisions: partition immutability, state-driven authority, retries scoped to failed partitions.  
  - Locked invariants: extractors write-only, validators own authority, no overwrites.

## Implementation of foundations

- [x] Stage 5 — Execution context & sink wiring  
  - Summary: Replaced ad-hoc writes with RunContext + RawSink plumbing in the pipeline.  
  - Key decisions: CLI generates run_id once; extractor writes directly to sink.

- [x] Stage 6 — State store implementation  
  - Summary: SQLite-based PartitionStateRepository with schema + CRUD ops.  
  - Key decisions: lazy creation, upsert semantics, ISO timestamps.

- [x] Stage 7 — Authority assignment (validator)  
  - Summary: RawPartitionValidator reads sink partitions, validates metadata, and records status.  
  - Key decisions: validator only writer, deterministic run_id selection, attempt tracking.

- [x] Stage 8 — Operator visibility  
  - Summary: Added `gads-etl state inspect` CLI for read-only visibility into authoritative partitions.  
  - Key decisions: filters, table/json output, zero side effects.

## Architecture still to define

- [ ] Stage 9 — Consumer contract  
- [ ] Stage 10 — Retry & orchestration semantics  
- [ ] Stage 11 — Storage realism (S3-compatible sink)  
- [ ] Stage 12 — Warehouse loading semantics  

## Non-architectural (later)

- [ ] Stage 13 — Observability  
- [ ] Stage 14 — Performance & scaling  

## Active Focus

- Current stage: Stage 9 — Consumer contract.  
- Why this stage matters: Consumers need a deterministic, state-driven contract before data can leave the raw layer; without it, downstream teams cannot rely on the pipeline.  
- What is explicitly NOT being worked on: retries/orchestration, S3 sink implementation, warehouse loaders, performance tuning.

## Open Decisions

- Decision: Consumer contract scope (Stage 9).  
- Options: (a) Minimal read spec that relies solely on state; (b) Broader contract including warehouse expectations.  
- Chosen: Pending — decision to be made before Stage 9 work begins.  
- Rationale: Need to balance short dev loops with clarity for downstream consumers; unresolved until Stage 9 design starts.
