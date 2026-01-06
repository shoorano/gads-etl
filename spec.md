## Purpose
This repository demonstrates a minimal, production-lean Google Ads ETL scaffold. It proves out credential handling, configuration management, and a working extraction loop so future work can focus on throughput and observability. All descriptions in this spec reflect the code as of today—no implied features.

The long-term intent is to run reliably on lean infrastructure (Hetzner-sized hosts) while remaining platform agnostic. Deterministic, idempotent pipelines and short developer feedback loops are guiding priorities as the system evolves.

## Operating principles
- Configuration is declarative and environment-driven; secrets never hard-coded.
- Prefer typed contracts (Pydantic models) to catch misconfiguration early.
- Keep extraction transparent by writing raw payloads before any transforms.
- Invest in tooling (CLI, scripts, tests) that run locally without services.

## Current system behavior
- **Entry points**: `gads-etl daily` and `gads-etl catch-up` (Typer CLI) call `PipelineRunner` modes. Helper scripts `scripts/generate_refresh_token.py` and `scripts/generate_token.py` mint OAuth refresh tokens (the latter depends on external modules not in this repo).
- **Extraction**: `GoogleAdsExtractor` issues GAQL queries defined in `config/google_apis.yaml`. Each query runs against the first configured customer id via `GoogleAdsService.search_stream`.
- **Output sink**: Raw rows are serialized to newline-delimited JSON files under `data/raw/<query_name>/<target_date>/payload.jsonl`. Each run overwrites the file for its query/date.
- **Configuration/env loading**: `.env` is auto-loaded on module import; `.env.test` overlays during pytest runs. `ConfigLoader` reads `config/google_apis.yaml`, which references env vars via `${VAR}` placeholders. `TEST_GOOGLE_ADS_*` variables are a naming convention for sandbox credentials.

## Guarantees
- GAQL fields listed in `config/google_apis.yaml` are fetched and written exactly as returned (converted to underscore-separated keys).
- The CLI runs without additional services beyond network access to Google Ads.
- Generated payload files contain every row yielded by Google Ads for the requested date range.

## Non-goals
- No state store or checkpointing table is maintained.
- No warehouse/destination loading occurs.
- No concurrency controls or transactional behavior exists.
- No schema drift or GAQL field migration logic is implemented.
- No retry/backoff customization or partial-failure handling is wired.

## Invariants for future development
- `.env` (and `.env.test` for tests) remains the single source of secrets; code must not ship with baked-in credentials.
- `config/google_apis.yaml` stays authoritative for defining extractors and must validate via Pydantic before execution.
- Every extraction writes a raw artifact before any transformations or loads.
- CLI commands must stay runnable from a vanilla checkout after `uv sync`.

## Known limitations (current)
- Importing `gads_etl.config` or `gads_etl.google_ads_client` immediately loads `.env`, which can surprise tooling.
- Only the first `customer_id` in config is queried; additional IDs are ignored.
- `PipelineRunner.sync_daily` materializes all rows in memory before writing.
- Multiple runs targeting the same query/date overwrite `payload.jsonl` with no locking.
- Output order mirrors Google Ads streaming order; it is not stabilized.
- Missing/renamed GAQL fields raise `AttributeError` and crash the run.
- Retry/backoff/partial-failure controls are left to google-ads defaults and are not set in code.

## Roadmap
1. Add deterministic batching and state tracking (per-query offsets).
2. Layer in warehouse loaders with idempotent upsert semantics.
3. Introduce configurable retry/backoff and partial-failure visibility.
4. Harden concurrency via file locking or partitioned outputs.

## Open questions
- Which orchestrator (cron, Prefect, Airflow) will drive production scheduling?
- What warehouse target (Postgres, BigQuery, etc.) will be standardized?
- How should multiple customer ids be partitioned—per run or per worker?
