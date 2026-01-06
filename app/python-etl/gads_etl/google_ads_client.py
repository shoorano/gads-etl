"""Helpers for building authenticated Google Ads API clients."""
import os
from typing import Dict

from google.ads.googleads.client import GoogleAdsClient

from .env import load_env

load_env()

REQUIRED_FIELDS = (
    "DEVELOPER_TOKEN",
    "CLIENT_ID",
    "CLIENT_SECRET",
    "REFRESH_TOKEN",
    "LOGIN_CUSTOMER_ID",
)


def _env_key(prefix: str, suffix: str) -> str:
    return f"{prefix}_{suffix}"


def _normalize_customer_id(value: str | None) -> str | None:
    if not value:
        return None
    return value.replace("-", "")


def load_google_ads_client(
    prefix: str = "GOOGLE_ADS", version: str | None = None
) -> GoogleAdsClient:
    """Instantiate a Google Ads client from environment variables."""
    prefix = prefix.upper()
    values: Dict[str, str] = {}
    missing: list[str] = []
    for field in REQUIRED_FIELDS:
        key = _env_key(prefix, field)
        value = os.getenv(key)
        if not value:
            missing.append(key)
        else:
            values[field] = value

    if missing:
        raise RuntimeError(
            "Missing Google Ads environment variables: {}".format(
                ", ".join(sorted(missing))
            )
        )

    linked_customer_id = _normalize_customer_id(
        os.getenv(_env_key(prefix, "CUSTOMER_ID"))
    )
    login_customer_id = _normalize_customer_id(values["LOGIN_CUSTOMER_ID"])
    config = {
        "developer_token": values["DEVELOPER_TOKEN"],
        "login_customer_id": login_customer_id,
        "use_proto_plus": True,
        "client_id": values["CLIENT_ID"],
        "client_secret": values["CLIENT_SECRET"],
        "refresh_token": values["REFRESH_TOKEN"],
    }
    if linked_customer_id:
        config["linked_customer_id"] = linked_customer_id

    version = version or os.getenv(_env_key(prefix, "API_VERSION")) or "v16"
    return GoogleAdsClient.load_from_dict(config, version=version)


__all__ = ["load_google_ads_client"]
