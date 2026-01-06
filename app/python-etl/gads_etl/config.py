"""Typed configuration loader for the ETL application."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, List

import yaml
from pydantic import BaseModel, Field, ValidationError, field_validator

from .env import load_env

load_env()


class QueryDefinition(BaseModel):
    name: str
    entity: str
    date_column: str = Field(..., description="Field used for incremental syncs")
    fields: List[str]


class GoogleAdsConfig(BaseModel):
    api_version: str
    login_customer_id: str
    manager_account_id: str
    customer_ids: List[str]
    ads_resource_queries: List[QueryDefinition] = Field(default_factory=list)
    incremental_keys: Dict[str, str] = Field(default_factory=dict)

    @field_validator("customer_ids", mode="before")
    @classmethod
    def _split_customer_ids(cls, value):
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("login_customer_id", "manager_account_id", mode="before")
    @classmethod
    def _ensure_string(cls, value):
        if value is None:
            return value
        return str(value)


class GoogleMerchantSchedule(BaseModel):
    name: str
    frequency: str
    chunk_size: int = 1000


class GoogleMerchantConfig(BaseModel):
    enabled: bool = False
    resource: str | None = None
    api_version: str | None = None
    merchant_id: str | None = None
    schedules: List[GoogleMerchantSchedule] = Field(default_factory=list)


class StorageConfig(BaseModel):
    warehouse_uri: str
    lake_bucket: str
    state_store_table: str


class MetadataConfig(BaseModel):
    dataset_timezone: str = "UTC"
    default_currency: str = "USD"
    catch_up_window_days: int = 30
    lookback_days_daily: int = 2


class ExtractorsConfig(BaseModel):
    google_ads: GoogleAdsConfig
    google_merchant: GoogleMerchantConfig | None = None


class PipelineConfig(BaseModel):
    metadata: MetadataConfig
    storage: StorageConfig
    extractors: ExtractorsConfig


class ConfigLoader:
    """Loads YAML driven configuration and validates it with Pydantic."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.config_path = Path(path or os.getenv("GADS_CONFIG_PATH", "config/google_apis.yaml"))
        if not self.config_path.exists():
            raise FileNotFoundError(f"Configuration file not found: {self.config_path}")
        self.model = self._parse_yaml()

    def _parse_yaml(self) -> PipelineConfig:
        raw: dict
        with self.config_path.open("r", encoding="utf-8") as fp:
            raw = yaml.safe_load(fp) or {}
        try:
            return PipelineConfig(**raw)
        except ValidationError as exc:  # pragma: no cover - surfacing error to CLI
            raise ValueError(f"Invalid configuration: {exc}") from exc

    def get_query(self, name: str) -> QueryDefinition:
        for query in self.model.extractors.google_ads.ads_resource_queries:
            if query.name == name:
                return query
        raise KeyError(f"Query definition '{name}' not found in configuration")


__all__ = [
    "ConfigLoader",
    "PipelineConfig",
]
