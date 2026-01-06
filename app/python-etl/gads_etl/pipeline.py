"""ETL orchestration primitives."""
from __future__ import annotations

import json
import logging
from datetime import date, timedelta
from pathlib import Path
from typing import Iterable, List

from google.ads.googleads.client import GoogleAdsClient

from .config import ConfigLoader, PipelineConfig, QueryDefinition
from .google_ads_client import load_google_ads_client

logger = logging.getLogger(__name__)


class GoogleAdsExtractor:
    """Pulls batched data using the official Google Ads API client."""

    def __init__(self, client: GoogleAdsClient, config: PipelineConfig) -> None:
        self.client = client
        self.config = config

    def fetch_incremental(
        self, query: QueryDefinition, start: date, end: date
    ) -> Iterable[dict]:
        service = self.client.get_service("GoogleAdsService")
        ga_query = self._build_query(query, start, end)
        search_request = self.client.get_type("SearchGoogleAdsStreamRequest")
        search_request.customer_id = self.config.extractors.google_ads.customer_ids[0]
        search_request.query = ga_query
        logger.info("Executing GAQL query %s", query.name)
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

    def __init__(self, config_loader: ConfigLoader | None = None) -> None:
        self.config_loader = config_loader or ConfigLoader()
        self.config = self.config_loader.model
        self.writer = LocalRawWriter()
        self.google_ads_client = self._build_google_ads_client()
        self.extractor = GoogleAdsExtractor(self.google_ads_client, self.config)

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
        for query in self.config.extractors.google_ads.ads_resource_queries:
            rows = list(self.extractor.fetch_incremental(query, start, target_date))
            self.writer.write(query.name, target_date, rows)

    def historical_catch_up(self, days: int | None = None) -> None:
        window = days or self.config.metadata.catch_up_window_days
        end = date.today()
        start = end - timedelta(days=window)
        logger.info("Running catch-up sync for %s - %s", start, end)
        self.sync_daily(target_date=end, lookback_days=window)


def run_pipeline(mode: str, days: int | None = None) -> None:
    runner = PipelineRunner()
    if mode == "daily":
        runner.sync_daily()
    elif mode == "catch-up":
        runner.historical_catch_up(days=days)
    else:
        raise ValueError(f"Unsupported mode: {mode}")
