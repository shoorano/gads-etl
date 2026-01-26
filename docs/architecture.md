# Architecture notes

- **Extraction** – Dedicated extractors read configuration from `config/google_apis.yaml` and issue batched requests to the Google Ads API. Each extractor emits raw payloads to object storage for traceability.
- **Load & transform** – Batches are normalized into structured tables using DuckDB or SQLAlchemy pipelines. Use manifests so reruns only process incomplete partitions.
- **Scheduling** – A lightweight orchestrator (Airflow, Dagster, Prefect, or a custom cron runner) drives daily syncs plus catch-up jobs for historical fills. Store job state in `STATE_STORE_TABLE` for idempotency.
- **Infrastructure** – Hetzner instances are provisioned with Ansible. Keep playbooks cloud agnostic by delegating provider specific setup to Terraform once the pipeline stabilizes.

See `docs/diagrams/system_overview.d2` and `docs/diagrams/timeline_single_partition.d2` for visual topology.
