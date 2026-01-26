"""Command line interface for the ETL."""
import logging
from datetime import date, datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

import typer

from .pipeline import run_pipeline
from .run_context import RunContext
from .state_store import PartitionStateRepository, PartitionState
from .state_inspect import format_states
from .raw_sink_local import LocalFilesystemRawSink
from .consumer_preview import render_preview, collect_preview
from .warehouse.pointer_store import SQLiteWarehousePointerStore
from .warehouse.loader import WarehouseLoader

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

logger = logging.getLogger(__name__)

app = typer.Typer(help="Google Ads ETL controller")
state_app = typer.Typer(help="State commands")
app.add_typer(state_app, name="state")
state_backfill_app = typer.Typer(help="Backfill control-plane commands")
state_app.add_typer(state_backfill_app, name="backfill")
consumer_app = typer.Typer(help="Read-only consumer helpers")
app.add_typer(consumer_app, name="consume")
warehouse_app = typer.Typer(help="Warehouse control-plane commands")
app.add_typer(warehouse_app, name="warehouse")
observe_app = typer.Typer(help="Observability commands")
app.add_typer(observe_app, name="observe")
retry_threshold = 20
backfill_threshold = 100


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
@state_app.command("retry")
def state_retry(
    customer_id: Optional[str] = typer.Option(None, "--customer-id"),
    query_name: Optional[str] = typer.Option(None, "--query-name"),
    since: Optional[str] = typer.Option(None, "--since"),
    until: Optional[str] = typer.Option(None, "--until"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    force: bool = typer.Option(False, "--force"),
    clear_terminal: bool = typer.Option(False, "--clear-terminal"),
    db_path: str = typer.Option("data/state_store.db", "--db-path"),
) -> None:
    """Requeue failed logical partitions by setting status to pending."""
    repo = PartitionStateRepository(db_path=db_path)
    if not Path(db_path).exists():
        typer.echo("State store not initialized; no records found.")
        raise typer.Exit(code=1)

    since_date = date.fromisoformat(since) if since else None
    until_date = date.fromisoformat(until) if until else None

    states = repo.list_partition_states(
        status="failed",
        customer_id=customer_id,
        query_name=query_name,
        since=since_date,
        until=until_date,
    )
    if not states:
        typer.echo("No failed partitions match the provided filters.")
        raise typer.Exit(code=0)

    if customer_id is None and query_name is None and since is None and until is None and not force:
        typer.echo("Refusing to retry everything without --force. Provide filters or use --force.")
        raise typer.Exit(code=1)

    if len(states) > retry_threshold and not force:
        typer.confirm(f"Retry {len(states)} partitions?", abort=True)

    pending_states = []
    terminal_blocked = []
    for state in states:
        if state.status != "failed":
            continue
        if state.error_message and "[terminal]" in state.error_message and not clear_terminal:
            terminal_blocked.append(state)
            continue
        pending_states.append(state)

    if not pending_states:
        typer.echo("No eligible partitions to retry (terminal or already pending).")
        raise typer.Exit(code=0)

    typer.echo(
        f"{'Dry-run' if dry_run else 'Executing'} retry for {len(pending_states)} partition(s) "
        f"[filters: customer={customer_id}, query={query_name}, since={since}, until={until}, "
        f"force={force}, clear_terminal={clear_terminal}]"
    )

    failures = 0
    for state in pending_states:
        log_line = (
            f"{state.customer_id} {state.query_name} {state.logical_date.isoformat()} "
            f"attempt_count={state.attempt_count}"
        )
        typer.echo(log_line)
        if dry_run:
            continue
        try:
            repo.upsert_partition_state(
                PartitionState(
                    source=state.source,
                    customer_id=state.customer_id,
                    query_name=state.query_name,
                    logical_date=state.logical_date,
                    status="pending",
                    current_run_id=state.current_run_id,
                    schema_version=state.schema_version,
                    record_count=state.record_count,
                    updated_at=datetime.now(timezone.utc),
                    error_message=None if clear_terminal else state.error_message,
                    attempt_count=state.attempt_count,
                )
            )
        except Exception as exc:  # pragma: no cover - best effort logging
            typer.echo(f"Failed to update {log_line}: {exc}", err=True)
            failures += 1

    if terminal_blocked and not clear_terminal:
        typer.echo(
            f"{len(terminal_blocked)} partition(s) blocked due to terminal state. "
            "Use --clear-terminal to override."
        )

    if failures:
        raise typer.Exit(code=1)


@warehouse_app.command("load")
def warehouse_load(
    state_db_path: str = typer.Option("data/state_store.db", "--state-db-path"),
    pointer_db_path: str = typer.Option("data/warehouse_pointers.db", "--pointer-db-path"),
) -> None:
    """Reconcile and publish warehouse pointers."""
    state_repo = PartitionStateRepository(db_path=state_db_path)
    pointer_store = SQLiteWarehousePointerStore(db_path=pointer_db_path)
    loader = WarehouseLoader(
        partition_state_repository=state_repo,
        pointer_store=pointer_store,
    )
    plan = loader.run()
    typer.echo(
        f"Warehouse reconciliation complete | loads={len(plan.load)} "
        f"replacements={len(plan.replace)} demotions={len(plan.demote)}"
    )


@observe_app.command("state")
def observe_state(
    db_path: str = typer.Option("data/state_store.db", "--db-path"),
    top_failed: int = typer.Option(10, "--top-failed", help="Top N failed partitions by attempts"),
) -> None:
    """Summarize pipeline state without mutating anything."""
    repo = PartitionStateRepository(db_path=db_path)
    states = repo.list_partition_states()
    if not states:
        typer.echo("No partition state records found.")
        raise typer.Exit(code=0)

    total = len(states)
    status_counts = {"pending": 0, "success": 0, "failed": 0}
    range_by_query: dict[tuple[str, str], tuple[str, str]] = {}
    attempt_values: list[int] = []
    failed_states = []

    for state in states:
        status_counts.setdefault(state.status, 0)
        status_counts[state.status] += 1
        key = (state.source, state.query_name)
        logical_date = state.logical_date.isoformat()
        min_date, max_date = range_by_query.get(key, (logical_date, logical_date))
        range_by_query[key] = (
            logical_date if logical_date < min_date else min_date,
            logical_date if logical_date > max_date else max_date,
        )
        attempts = state.attempt_count or 0
        attempt_values.append(attempts)
        if state.status == "failed":
            failed_states.append(state)

    attempt_min = min(attempt_values) if attempt_values else 0
    attempt_max = max(attempt_values) if attempt_values else 0
    attempt_avg = (
        sum(attempt_values) / len(attempt_values) if attempt_values else 0.0
    )

    typer.echo(f"Total logical partitions: {total}")
    typer.echo("Status counts:")
    for status in ("pending", "success", "failed"):
        typer.echo(f"  {status}: {status_counts.get(status, 0)}")

    typer.echo("Date ranges by (source, query_name):")
    for key in sorted(range_by_query):
        min_date, max_date = range_by_query[key]
        typer.echo(f"  {key[0]} / {key[1]} :: {min_date} -> {max_date}")

    typer.echo(
        "Attempt counts: "
        f"min={attempt_min} max={attempt_max} avg={attempt_avg:.2f}"
    )

    failed_sorted = sorted(
        failed_states,
        key=lambda s: (
            -(s.attempt_count or 0),
            s.customer_id,
            s.query_name,
            s.logical_date.isoformat(),
        ),
    )
    typer.echo(f"Top {min(top_failed, len(failed_sorted))} failed partitions:")
    for state in failed_sorted[:top_failed]:
        typer.echo(
            f"  {state.customer_id} {state.query_name} {state.logical_date.isoformat()} "
            f"attempts={state.attempt_count or 0} updated_at={state.updated_at.isoformat()}"
        )
    if not failed_states:
        typer.echo("  (none)")

    oldest_failed = min(
        failed_states, key=lambda s: s.updated_at
    ) if failed_states else None
    if oldest_failed:
        typer.echo(
            "Oldest failed partition: "
            f"{oldest_failed.customer_id} {oldest_failed.query_name} "
            f"{oldest_failed.logical_date.isoformat()} updated_at={oldest_failed.updated_at.isoformat()}"
        )
    else:
        typer.echo("Oldest failed partition: (none)")


@observe_app.command("freshness")
def observe_freshness(
    db_path: str = typer.Option("data/state_store.db", "--db-path"),
) -> None:
    """Report freshness and gaps for successful partitions."""
    repo = PartitionStateRepository(db_path=db_path)
    states = repo.list_partition_states(status="success")
    if not states:
        typer.echo("No successful partitions found.")
        raise typer.Exit(code=0)

    today = date.today()
    grouped: dict[tuple[str, str], set[date]] = {}
    for state in states:
        key = (state.source, state.query_name)
        grouped.setdefault(key, set()).add(state.logical_date)

    for key in sorted(grouped.keys()):
        dates = sorted(grouped[key])
        earliest = dates[0]
        latest = dates[-1]
        lag_days = (today - latest).days
        total = len(dates)
    typer.echo(f"{key[0]} / {key[1]}")
    typer.echo(f"  earliest: {earliest.isoformat()}")
    typer.echo(f"  latest: {latest.isoformat()} (lag_days={lag_days})")
    typer.echo(f"  total_successful_partitions: {total}")

        gaps = _find_date_gaps(dates)
        if gaps:
            typer.echo("  gaps:")
            for start, end in gaps:
                if start == end:
                    typer.echo(f"    {start.isoformat()}")
                else:
                    typer.echo(
                        f"    {start.isoformat()} -> {end.isoformat()}"
                    )
        else:
            typer.echo("  gaps: none")


def _find_date_gaps(sorted_dates: list[date]) -> list[tuple[date, date]]:
    """Identify missing logical dates between earliest and latest."""
    if len(sorted_dates) < 2:
        return []
    date_set = set(sorted_dates)
    gaps = []
    current = sorted_dates[0]
    end = sorted_dates[-1]
    while current <= end:
        if current not in date_set:
            gap_start = current
            while current <= end and current not in date_set:
                current += timedelta(days=1)
            gap_end = current - timedelta(days=1)
            gaps.append((gap_start, gap_end))
            continue
        current += timedelta(days=1)
    return gaps


@observe_app.command("retries")
def observe_retries(
    db_path: str = typer.Option("data/state_store.db", "--db-path"),
    top_partitions: int = typer.Option(
        10, "--top", help="Top N partitions by attempt count"
    ),
) -> None:
    """Summarize retry and failure patterns without mutating state."""
    repo = PartitionStateRepository(db_path=db_path)
    states = repo.list_partition_states()
    if not states:
        typer.echo("No partition state records found.")
        raise typer.Exit(code=0)

    total = len(states)
    failed = [s for s in states if s.status == "failed"]
    terminal = [
        s for s in failed if s.error_message and "[terminal]" in s.error_message
    ]
    retryable_failed = [s for s in failed if s not in terminal]

    attempt_counts = [s.attempt_count or 0 for s in states]
    attempt_min = min(attempt_counts) if attempt_counts else 0
    attempt_max = max(attempt_counts) if attempt_counts else 0
    attempt_avg = (
        sum(attempt_counts) / len(attempt_counts) if attempt_counts else 0.0
    )

    typer.echo("Retry overview")
    typer.echo(f"  total partitions: {total}")
    typer.echo(f"  failed partitions: {len(failed)}")
    typer.echo(f"  terminal partitions: {len(terminal)}")
    typer.echo(f"  retryable failed partitions: {len(retryable_failed)}")
    typer.echo(
        "  attempt counts: "
        f"min={attempt_min} max={attempt_max} avg={attempt_avg:.2f}"
    )

    buckets = {
        "1-2": 0,
        "3-5": 0,
        "6-10": 0,
        "10+": 0,
    }
    for attempts in attempt_counts:
        if attempts <= 2:
            buckets["1-2"] += 1
        elif attempts <= 5:
            buckets["3-5"] += 1
        elif attempts <= 10:
            buckets["6-10"] += 1
        else:
            buckets["10+"] += 1
    typer.echo("  attempt histogram:")
    for label in ("1-2", "3-5", "6-10", "10+"):
        typer.echo(f"    {label}: {buckets[label]}")

    hot_partitions = sorted(
        states,
        key=lambda s: (
            -(s.attempt_count or 0),
            s.status != "failed",
            s.customer_id,
            s.query_name,
            s.logical_date.isoformat(),
        ),
    )[:top_partitions]
    typer.echo(f"Top {min(top_partitions, len(states))} partitions by attempts:")
    for state in hot_partitions:
        typer.echo(
            f"  {state.customer_id} {state.query_name} {state.logical_date.isoformat()} "
            f"attempts={state.attempt_count or 0} status={state.status} "
            f"updated_at={state.updated_at.isoformat()}"
        )

    if failed:
        oldest_failed = min(failed, key=lambda s: s.updated_at)
        newest_failed = max(failed, key=lambda s: s.updated_at)
        typer.echo(
            "Oldest failed partition: "
            f"{oldest_failed.customer_id} {oldest_failed.query_name} "
            f"{oldest_failed.logical_date.isoformat()} updated_at={oldest_failed.updated_at.isoformat()}"
        )
        typer.echo(
            "Newest failed partition: "
            f"{newest_failed.customer_id} {newest_failed.query_name} "
            f"{newest_failed.logical_date.isoformat()} updated_at={newest_failed.updated_at.isoformat()}"
        )
    else:
        typer.echo("No failed partitions present.")


@state_app.command("mark-terminal")
def state_mark_terminal(
    customer_id: Optional[str] = typer.Option(None, "--customer-id"),
    query_name: Optional[str] = typer.Option(None, "--query-name"),
    since: Optional[str] = typer.Option(None, "--since"),
    until: Optional[str] = typer.Option(None, "--until"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    force: bool = typer.Option(False, "--force"),
    db_path: str = typer.Option("data/state_store.db", "--db-path"),
) -> None:
    """Mark failed logical partitions as terminal (no automatic retries)."""
    repo = PartitionStateRepository(db_path=db_path)
    if not Path(db_path).exists():
        typer.echo("State store not initialized; no records found.")
        raise typer.Exit(code=1)

    since_date = date.fromisoformat(since) if since else None
    until_date = date.fromisoformat(until) if until else None

    states = repo.list_partition_states(
        status="failed",
        customer_id=customer_id,
        query_name=query_name,
        since=since_date,
        until=until_date,
    )
    if not states:
        typer.echo("No failed partitions match the provided filters.")
        raise typer.Exit(code=0)

    if customer_id is None and query_name is None and since is None and until is None and not force:
        typer.echo("Refusing to mark all partitions terminal without --force. Provide filters or use --force.")
        raise typer.Exit(code=1)

    if len(states) > retry_threshold and not force:
        typer.confirm(f"Mark {len(states)} partitions terminal?", abort=True)

    already_terminal = []
    candidates = []
    for state in states:
        if state.error_message and "[terminal]" in state.error_message:
            already_terminal.append(state)
            continue
        candidates.append(state)

    if not candidates:
        typer.echo("All selected partitions are already terminal.")
        raise typer.Exit(code=0)

    typer.echo(
        f"{'Dry-run' if dry_run else 'Executing'} mark-terminal for {len(candidates)} partition(s) "
        f"[filters: customer={customer_id}, query={query_name}, since={since}, until={until}, force={force}]"
    )

    failures = 0
    for state in candidates:
        log_line = (
            f"{state.customer_id} {state.query_name} {state.logical_date.isoformat()} "
            f"attempt_count={state.attempt_count}"
        )
        typer.echo(log_line)
        if dry_run:
            continue
        try:
            repo.upsert_partition_state(
                PartitionState(
                    source=state.source,
                    customer_id=state.customer_id,
                    query_name=state.query_name,
                    logical_date=state.logical_date,
                    status="failed",
                    current_run_id=state.current_run_id,
                    schema_version=state.schema_version,
                    record_count=state.record_count,
                    updated_at=datetime.now(timezone.utc),
                    error_message=_terminal_message(state),
                    attempt_count=state.attempt_count,
                )
            )
        except Exception as exc:
            typer.echo(f"Failed to update {log_line}: {exc}", err=True)
            failures += 1

    if failures:
        raise typer.Exit(code=1)


@state_backfill_app.command("enqueue")
def state_backfill_enqueue(
    customer_id: str = typer.Option(..., "--customer-id"),
    query_name: str = typer.Option(..., "--query-name"),
    since: str = typer.Option(..., "--since"),
    until: str = typer.Option(..., "--until"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    force_pending: bool = typer.Option(False, "--force-pending"),
    force: bool = typer.Option(False, "--force"),
    db_path: str = typer.Option("data/state_store.db", "--db-path"),
) -> None:
    """Enqueue historical logical partitions as pending."""
    repo = PartitionStateRepository(db_path=db_path)
    if not Path(db_path).exists():
        typer.echo("State store not initialized; no records found.")
        raise typer.Exit(code=1)

    since_date = date.fromisoformat(since)
    until_date = date.fromisoformat(until)
    if since_date > until_date:
        typer.echo("since must be <= until")
        raise typer.Exit(code=1)

    dates = []
    cursor = since_date
    while cursor <= until_date:
        dates.append(cursor)
        cursor += timedelta(days=1)

    if len(dates) > backfill_threshold and not force:
        typer.confirm(f"Enqueue {len(dates)} partitions?", abort=True)

    typer.echo(
        f"{'Dry-run' if dry_run else 'Enqueueing'} backfill for customer={customer_id} "
        f"query={query_name} dates={since}..{until} count={len(dates)} force_pending={force_pending}"
    )

    failures = 0
    enqueued = 0
    skipped = 0
    for logical_date in dates:
        state = repo.get_partition_state(
            source="google_ads",
            customer_id=customer_id,
            query_name=query_name,
            logical_date=logical_date,
        )
        if state and not force_pending:
            typer.echo(
                f"Skipping {customer_id} {query_name} {logical_date}: status={state.status}"
            )
            skipped += 1
            continue

        typer.echo(
            f"{'Would enqueue' if dry_run else 'Enqueueing'} {customer_id} {query_name} {logical_date}"
        )
        enqueued += 1
        if dry_run:
            continue
        try:
            repo.upsert_partition_state(
                PartitionState(
                    source="google_ads",
                    customer_id=customer_id,
                    query_name=query_name,
                    logical_date=logical_date,
                    status="pending",
                    current_run_id=state.current_run_id if state and force_pending else None,
                    schema_version=state.schema_version if state else None,
                    record_count=state.record_count if state else None,
                    updated_at=datetime.now(timezone.utc),
                    error_message=None,
                    attempt_count=state.attempt_count if state else 0,
                )
            )
        except Exception as exc:
            typer.echo(
                f"Failed to enqueue {customer_id} {query_name} {logical_date}: {exc}", err=True
            )
            failures += 1

    typer.echo(f"Enqueued={enqueued} skipped={skipped} failures={failures}")
    if failures:
        raise typer.Exit(code=1)


def _terminal_message(state: PartitionState) -> str:
    base = state.error_message or ""
    marker = "[terminal]"
    if marker in base:
        return base
    if base:
        return f"{marker} {base}"
    return marker
