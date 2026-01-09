"""Core package for the Google Ads ETL pipeline."""
from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("gads-etl")
except PackageNotFoundError:  # pragma: no cover - during local dev without install
    __version__ = "0.0.0"

__all__ = ["__version__"]
