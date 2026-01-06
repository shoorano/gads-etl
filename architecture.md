## Current architecture

### Flow
`gads-etl` commands (Typer CLI) invoke `PipelineRunner`, which orchestrates the following path:
`CLI (app/python-etl/gads_etl/cli.py)` → `run_pipeline` → `PipelineRunner` → `GoogleAdsExtractor` → `LocalRawWriter`.

```
           +-----------+      +----------------+      +------------------+      +----------------+
CLI/cron ->| Typer CLI |----->| PipelineRunner |----->| GoogleAdsExtractor|----->| LocalRawWriter |
           +-----------+      +----------------+      +------------------+      +----------------+
                                                            |
                                                            v
                                                   Google Ads API (GAQL)
```

### Configuration flow
- Secrets: `.env` (runtime) and `.env.test` (tests) hold `GOOGLE_ADS_*` / `TEST_GOOGLE_ADS_*` variables. They are loaded automatically when `gads_etl.config` or `gads_etl.google_ads_client` is imported.
- Declarative config: `config/google_apis.yaml` contains metadata, storage pointers, and GAQL query definitions. `ConfigLoader` (Pydantic) validates the file and exposes typed models to `PipelineRunner`.

### Storage
- `LocalRawWriter` writes newline-delimited JSON files to `data/raw/<query>/<date>/payload.jsonl`. There is no other persistence layer, warehouse sink, or checkpoint store today.

## Intended target architecture
- **Storage layers**: raw payloads land in an object store (S3/GCS) partitioned by extraction date, query name, and customer id. Curated tables live in a warehouse (Postgres/BigQuery) with schema migrations.
- **State management**: maintain a durable state store (e.g., Postgres table) tracking per-query/customer offsets (date cursors, job status) to support idempotent ingest and replay.
- **Processing**: ingestion should be restartable and rerunnable. Every load must be idempotent by design (upsert or replace partitions). Partition keys follow `<customer_id>/<query_name>/<YYYY-MM-DD>`.

## Production deployment model
- Baseline provisioning uses `infra/ansible` to configure Hetzner-style hosts. Expect systemd services or timers to invoke CLI commands on schedule.
- Secrets currently live in `/etc/gads-etl/.env`; future direction is to source from a managed secret store (Vault/SOPS/parameter store) injected at deploy time.

## Local development model
- Priority is fast iteration: clone repo, `uv sync`, run CLI/tests without extra services. `.env` and `.env.test` provide all credentials needed for unit/integration loops.
- Containers may be introduced for parity (e.g., docker-compose with Postgres/MinIO) but are optional. The authoritative workflow remains “local tooling + remote APIs”.

## Determinism & idempotency model
- Today: determinism relies solely on GAQL filters (date ranges). The same run overwrites its output file; there’s no checkpointing or dedupe.
- Future: enforce deterministic partition writes, track processing state per partition, and guarantee that reprocessing produces identical artifacts or safely supersedes prior data.

## Observability and logging
- Current logging: standard `logging.basicConfig` to stdout (`gads_etl/cli.py`). No structured logs, metrics, or tracing.
- Desired: structured logs with query/date/customer tags, metrics on extraction counts and latency, and hooks for distributed tracing once orchestrated.
