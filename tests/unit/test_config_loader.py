"""Unit tests for the configuration loader."""
from __future__ import annotations

from pathlib import Path

from gads_etl.config import ConfigLoader


def test_config_loader_parses_customer_ids(tmp_path: Path) -> None:
    config_payload = """
    metadata:
      dataset_timezone: UTC
      catch_up_window_days: 10
      lookback_days_daily: 1
    storage:
      warehouse_uri: postgres://example
      lake_bucket: s3://example
      state_store_table: etl_state
    extractors:
      google_ads:
        api_version: v22
        login_customer_id: 1111111111
        manager_account_id: 2222222222
        customer_ids: "3333333333, 4444444444"
        ads_resource_queries:
          - name: sample_query
            entity: campaign
            date_column: segments.date
            fields:
              - campaign.id
        incremental_keys:
          sample_query: segments.date
      google_merchant:
        enabled: false
    """
    config_file = tmp_path / "config.yaml"
    config_file.write_text(config_payload)

    loader = ConfigLoader(path=config_file)

    customer_ids = loader.model.extractors.google_ads.customer_ids
    assert customer_ids == ["3333333333", "4444444444"]
    query = loader.get_query("sample_query")
    assert query.entity == "campaign"
    assert query.fields == ["campaign.id"]
