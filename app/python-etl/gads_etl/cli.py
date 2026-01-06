"""Command line interface for the ETL."""
from __future__ import annotations

import logging
from typing import Optional

import typer

from .pipeline import run_pipeline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

app = typer.Typer(help="Google Ads ETL controller")


@app.command()
def daily() -> None:
    """Run the daily incremental sync."""
    run_pipeline(mode="daily")


@app.command("catch-up")
def catch_up(days: Optional[int] = typer.Option(None, help="Override default catch-up window")) -> None:
    """Backfill a range of dates."""
    run_pipeline(mode="catch-up", days=days)


if __name__ == "__main__":
    app()
