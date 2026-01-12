"""ETL orchestration primitives."""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

from google.ads.googleads.client import GoogleAdsClient

from .config import ConfigLoader, PipelineConfig, QueryDefinition
from .google_ads_client import load_google_ads_client
from .raw_sink import PartitionKey, RawSink
from .raw_sink_factory import create_raw_sink
from .run_context import RunContext

logger = logging.getLogger(__name__)


class GoogleAdsExtractor:
    """Pulls batched data using the official Google Ads API client."""

    source_name = "google_ads"

    def __init__(
        self,
        client: GoogleAdsClient,
        config: PipelineConfig,
        run_context: RunContext,
        raw_sink: RawSink,
    ) -> None:
        self.client = client
        self.config = config
        self.run_context = run_context
        self.raw_sink = raw_sink

    def extract_partition(
        self,
        query: QueryDefinition,
        customer_id: str,
        logical_date: str,
        start: date,
        end: date,
    ) -> None:
        partition_key = PartitionKey(
            source=self.source_name,
            customer_id=customer_id,
            query_name=query.name,
            logical_date=logical_date,
        )
        ga_query = self._build_query(query, start, end)
        writer = self.raw_sink.write_partition(partition_key, self.run_context.run_id)
        record_count = 0
        logger.info(
            "Executing GAQL query %s for customer %s run_id=%s",
            query.name,
            customer_id,
            self.run_context.run_id,
        )

        for row in self._stream_rows(query, ga_query, customer_id):
            writer.write_payload_row(row)
            record_count += 1

        metadata = {
            "source": partition_key.source,
            "customer_id": partition_key.customer_id,
            "query_name": partition_key.query_name,
            "logical_date": partition_key.logical_date,
            "run_id": self.run_context.run_id,
            "extracted_at": self._now_iso(),
            "schema_version": "v1",
            "record_count": record_count,
            "api_version": self.config.extractors.google_ads.api_version,
            "query_signature": ga_query,
        }
        writer.finalize(metadata)

    def _stream_rows(
        self, query: QueryDefinition, ga_query: str, customer_id: str
    ) -> Iterable[dict]:
        service = self.client.get_service("GoogleAdsService")
        search_request = self.client.get_type("SearchGoogleAdsStreamRequest")
        search_request.customer_id = customer_id
        search_request.query = ga_query
        stream = service.search_stream(search_request)
        for batch in stream:
            for row in batch.results:
                yield self._row_to_dict(row, query)

    def _build_query(self, query: QueryDefinition, start: date, end: date) -> str:
        fields = ", ".join(query.fields)
        return (
            f"SELECT {fields} FROM {query.entity} "
            f"WHERE {query.date_column} BETWEEN '{start}' AND '{end}'"
        )

    def _row_to_dict(self, row, query: QueryDefinition) -> dict:
        payload = {}
        for field in query.fields:
            cursor = row
            for part in field.split("."):
                cursor = getattr(cursor, part)
            payload[field.replace(".", "_")] = cursor
        payload["__query_name"] = query.name
        return payload

    @staticmethod
    def _now_iso() -> str:
        return (
            datetime.now(timezone.utc)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z")
        )


class LocalRawWriter:
    """Persists raw payloads to disk for replay/debugging."""

    def __init__(self, root: Path = Path("data/raw")) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def write(self, query_name: str, partition_date: date, rows: Iterable[dict]) -> Path:
        partition_dir = self.root / query_name / partition_date.isoformat()
        partition_dir.mkdir(parents=True, exist_ok=True)
        file_path = partition_dir / "payload.jsonl"
        written = 0
        with file_path.open("w", encoding="utf-8") as fp:
            for row in rows:
                fp.write(json.dumps(row) + "\n")
                written += 1
        logger.info("Wrote %s rows for %s", written, query_name)
        return file_path


class PipelineRunner:
    """Coordinates extraction and loading steps."""

    def __init__(
        self,
        config_loader: ConfigLoader | None = None,
        run_context: RunContext | None = None,
    ) -> None:
        self.config_loader = config_loader or ConfigLoader()
        self.config = self.config_loader.model
        self.run_context = run_context or RunContext.create()
        self.google_ads_client = self._build_google_ads_client()
        self.raw_sink = create_raw_sink()
        self.extractor = GoogleAdsExtractor(
            self.google_ads_client,
            self.config,
            self.run_context,
            self.raw_sink,
        )

    def _build_google_ads_client(self) -> GoogleAdsClient:
        return load_google_ads_client(
            prefix="GOOGLE_ADS",
            version=self.config.extractors.google_ads.api_version,
        )

    def sync_daily(self, target_date: date | None = None, lookback_days: int | None = None) -> None:
        target_date = target_date or date.today()
        lookback = lookback_days or self.config.metadata.lookback_days_daily
        start = target_date - timedelta(days=lookback)
        logger.info("Running daily sync for %s - %s", start, target_date)
        logical_date = target_date.isoformat()
        for query in self.config.extractors.google_ads.ads_resource_queries:
            for customer_id in self.config.extractors.google_ads.customer_ids:
                self.extractor.extract_partition(
                    query=query,
                    customer_id=customer_id,
                    logical_date=logical_date,
                    start=start,
                    end=target_date,
                )

    def historical_catch_up(self, days: int | None = None) -> None:
        window = days or self.config.metadata.catch_up_window_days
        end = date.today()
        start = end - timedelta(days=window)
        logger.info("Running catch-up sync for %s - %s", start, end)
        self.sync_daily(target_date=end, lookback_days=window)


def run_pipeline(
    mode: str, days: int | None = None, run_context: RunContext | None = None
) -> None:
    runner = PipelineRunner(run_context=run_context)
    if mode == "daily":
        runner.sync_daily()
    elif mode == "catch-up":
        runner.historical_catch_up(days=days)
    else:
        raise ValueError(f"Unsupported mode: {mode}")
