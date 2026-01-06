"""Integration test that verifies access to the Google Ads API."""
from __future__ import annotations

import os

import pytest

from gads_etl.google_ads_client import load_google_ads_client

pytestmark = pytest.mark.integration

REQUIRED_ENV_VARS = (
    "TEST_GOOGLE_ADS_DEVELOPER_TOKEN",
    "TEST_GOOGLE_ADS_CLIENT_ID",
    "TEST_GOOGLE_ADS_CLIENT_SECRET",
    "TEST_GOOGLE_ADS_REFRESH_TOKEN",
    "TEST_GOOGLE_ADS_LOGIN_CUSTOMER_ID",
)


def _require_test_credentials() -> None:
    missing = [env for env in REQUIRED_ENV_VARS if not os.getenv(env)]
    if missing:
        pytest.fail(
            "Missing Google Ads sandbox credentials. "
            "Set the following env vars before running integration tests: "
            f"{', '.join(sorted(missing))}"
        )


def test_customer_service_lists_accessible_accounts() -> None:
    """Calls CustomerService.list_accessible_customers to ensure OAuth setup works.

    Based on the sample documented in the Google Ads API (see v22 GAQL examples).
    """
    _require_test_credentials()
    version = os.getenv("TEST_GOOGLE_ADS_API_VERSION")
    client = load_google_ads_client(prefix="TEST_GOOGLE_ADS", version=version)
    customer_service = client.get_service("CustomerService")
    response = customer_service.list_accessible_customers()

    resource_names = list(response.resource_names)
    print(resource_names)
    assert resource_names, "Expected at least one accessible customer resource name"
