"""Command line interface for the ETL."""
import logging
from datetime import date
from pathlib import Path
from typing import Optional

import typer

from .pipeline import run_pipeline
from .run_context import RunContext
from .state_store import PartitionStateRepository
from .state_inspect import format_states
from .raw_sink_local import LocalFilesystemRawSink
from .consumer_preview import render_preview, collect_preview

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

logger = logging.getLogger(__name__)

app = typer.Typer(help="Google Ads ETL controller")
state_app = typer.Typer(help="State inspection commands")
app.add_typer(state_app, name="state")
consumer_app = typer.Typer(help="Read-only consumer helpers")
app.add_typer(consumer_app, name="consume")


@app.command()
def daily() -> None:
    """Run the daily incremental sync."""
    run_context = RunContext.create()
    logger.info("Starting daily run with run_id=%s", run_context.run_id)
    run_pipeline(mode="daily", run_context=run_context)


@app.command("catch-up")
def catch_up(
    days: Optional[int] = typer.Option(None, help="Override default catch-up window")
) -> None:
    """Backfill a range of dates."""
    run_context = RunContext.create()
    logger.info(
        "Starting catch-up run with run_id=%s days=%s", run_context.run_id, days
    )
    run_pipeline(mode="catch-up", days=days, run_context=run_context)


@state_app.command("inspect")
def state_inspect(
    status: Optional[str] = typer.Option(None, "--status"),
    customer_id: Optional[str] = typer.Option(None, "--customer-id"),
    query_name: Optional[str] = typer.Option(None, "--query-name"),
    since: Optional[str] = typer.Option(None, "--since"),
    until: Optional[str] = typer.Option(None, "--until"),
    limit: Optional[int] = typer.Option(None, "--limit"),
    output_format: str = typer.Option("table", "--format", help="table or json"),
    db_path: str = typer.Option("data/state_store.db", "--db-path"),
) -> None:
    """Inspect current partition state without mutating anything."""
    repo = PartitionStateRepository(db_path=db_path)
    if not Path(db_path).exists():
        typer.echo("State store not initialized; no records found.")
        raise typer.Exit(code=0)

    since_date = date.fromisoformat(since) if since else None
    until_date = date.fromisoformat(until) if until else None

    states = repo.list_partition_states(
        status=status,
        customer_id=customer_id,
        query_name=query_name,
        since=since_date,
        until=until_date,
        limit=limit,
    )
    if not states:
        typer.echo("No partition state records found.")
        raise typer.Exit(code=0)
    typer.echo(format_states(states, output_format=output_format))


@consumer_app.command("preview")
def consume_preview(
    customer_id: Optional[str] = typer.Option(None, "--customer-id"),
    query_name: Optional[str] = typer.Option(None, "--query-name"),
    since: Optional[str] = typer.Option(None, "--since"),
    until: Optional[str] = typer.Option(None, "--until"),
    limit_partitions: Optional[int] = typer.Option(None, "--limit-partitions"),
    sample_rows: int = typer.Option(5, "--sample-rows"),
    output_format: str = typer.Option("table", "--format", help="table or json"),
    db_path: str = typer.Option("data/state_store.db", "--db-path"),
    sink_root: str = typer.Option("data/raw", "--raw-root"),
) -> None:
    """Preview authoritative partitions without writing anywhere."""
    repo = PartitionStateRepository(db_path=db_path)
    if not Path(db_path).exists():
        typer.echo("State store not initialized; no records found.")
        raise typer.Exit(code=1)

    since_date = date.fromisoformat(since) if since else None
    until_date = date.fromisoformat(until) if until else None

    states = repo.list_partition_states(
        status="success",
        customer_id=customer_id,
        query_name=query_name,
        since=since_date,
        until=until_date,
        limit=limit_partitions,
    )
    if not states:
        typer.echo("No authoritative partitions found.")
        raise typer.Exit(code=0)

    sink = LocalFilesystemRawSink(root=sink_root)
    previews = collect_preview(
        sink=sink,
        partitions=states,
        sample_rows=sample_rows,
    )
    typer.echo(render_preview(previews, output_format=output_format))


if __name__ == "__main__":
    app()
