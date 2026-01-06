# Storage design

The ETL persists data in two layers:

1. **Raw data lake** – compressed parquet/JSON exported directly from Google APIs and stored in the `DATA_LAKE_BUCKET` bucket. Objects are partitioned by `source/date` to keep daily syncs cheap.
2. **Serving warehouse** – a relational engine (DuckDB, PostgreSQL, BigQuery, etc.) reachable at `WAREHOUSE_URI`. Daily jobs upsert into slowly changing dimension tables plus fact tables optimized for dashboard queries.

`schema/warehouse_tables.sql` contains a starter definition for canonical fact tables. Update it as the data model evolves. Migrations should live in `database/migrations/` once a tool such as Alembic is introduced.
