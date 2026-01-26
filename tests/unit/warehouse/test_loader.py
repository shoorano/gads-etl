from datetime import date, datetime, timezone

from gads_etl.state_store import PartitionState, PartitionStateRepository
from gads_etl.warehouse.loader import WarehouseLoader
from gads_etl.warehouse.pointer_store import (
    SQLiteWarehousePointerStore,
    WarehousePointer,
)


def _make_state_repo(tmp_path):
    path = tmp_path / "state.db"
    repo = PartitionStateRepository(db_path=path)
    repo.ensure_schema()
    return repo


def _make_pointer_store(tmp_path):
    path = tmp_path / "warehouse_pointers.db"
    store = SQLiteWarehousePointerStore(db_path=str(path))
    return store


def _success_state(
    run_id: str,
    logical_date: date = date(2024, 1, 1),
) -> PartitionState:
    return PartitionState(
        source="google_ads",
        customer_id="123",
        query_name="campaign_stats",
        logical_date=logical_date,
        status="success",
        current_run_id=run_id,
        schema_version="v1",
        record_count=10,
        updated_at=datetime.now(timezone.utc),
        error_message=None,
        attempt_count=1,
    )


def _upsert_state(repo: PartitionStateRepository, state: PartitionState):
    repo.upsert_partition_state(state)


def _insert_pointer(store: SQLiteWarehousePointerStore, pointer: WarehousePointer):
    store.upsert_pointer(pointer)


def test_reconcile_load_target(tmp_path):
    repo = _make_state_repo(tmp_path)
    store = _make_pointer_store(tmp_path)
    _upsert_state(repo, _success_state("run-load"))

    loader = WarehouseLoader(repo, store)
    plan = loader._reconcile_partitions()

    assert len(plan.load) == 1
    target = plan.load[0]
    assert target.run_id == "run-load"
    assert plan.replace == ()
    assert plan.demote == ()


def test_reconcile_replace_target(tmp_path):
    repo = _make_state_repo(tmp_path)
    store = _make_pointer_store(tmp_path)
    _upsert_state(repo, _success_state("run-new"))
    _insert_pointer(
        store,
        WarehousePointer(
            source="google_ads",
            customer_id="123",
            query_name="campaign_stats",
            logical_date="2024-01-01",
            run_id="run-old",
            schema_version="v1",
            loaded_at=datetime.now(timezone.utc).isoformat(),
        ),
    )

    loader = WarehouseLoader(repo, store)
    plan = loader._reconcile_partitions()

    assert len(plan.replace) == 1
    assert plan.replace[0].run_id == "run-new"
    assert plan.load == ()


def test_reconcile_noop(tmp_path):
    repo = _make_state_repo(tmp_path)
    store = _make_pointer_store(tmp_path)
    _upsert_state(repo, _success_state("run-same"))
    _insert_pointer(
        store,
        WarehousePointer(
            source="google_ads",
            customer_id="123",
            query_name="campaign_stats",
            logical_date="2024-01-01",
            run_id="run-same",
            schema_version="v1",
            loaded_at=datetime.now(timezone.utc).isoformat(),
        ),
    )

    loader = WarehouseLoader(repo, store)
    plan = loader._reconcile_partitions()

    assert plan.load == ()
    assert plan.replace == ()
    assert plan.demote == ()


def test_reconcile_demote(tmp_path):
    repo = _make_state_repo(tmp_path)
    store = _make_pointer_store(tmp_path)
    _insert_pointer(
        store,
        WarehousePointer(
            source="google_ads",
            customer_id="123",
            query_name="campaign_stats",
            logical_date="2024-01-01",
            run_id="stale-run",
            schema_version="v1",
            loaded_at=datetime.now(timezone.utc).isoformat(),
        ),
    )

    loader = WarehouseLoader(repo, store)
    plan = loader._reconcile_partitions()

    assert len(plan.demote) == 1
    assert plan.demote[0].run_id == "stale-run"
    assert plan.load == ()
    assert plan.replace == ()


def test_publish_updates_and_demotes(tmp_path):
    repo = _make_state_repo(tmp_path)
    store = _make_pointer_store(tmp_path)
    # Partition needing load
    _upsert_state(repo, _success_state("run-load", logical_date=date(2024, 1, 1)))
    # Partition needing replace
    _upsert_state(
        repo,
        _success_state("run-new", logical_date=date(2024, 1, 2)),
    )
    _insert_pointer(
        store,
        WarehousePointer(
            source="google_ads",
            customer_id="123",
            query_name="campaign_stats",
            logical_date="2024-01-02",
            run_id="run-old",
            schema_version="v1",
            loaded_at=datetime.now(timezone.utc).isoformat(),
        ),
    )
    # Partition needing demotion
    _insert_pointer(
        store,
        WarehousePointer(
            source="google_ads",
            customer_id="123",
            query_name="campaign_stats",
            logical_date="2024-01-03",
            run_id="obsolete-run",
            schema_version="v1",
            loaded_at=datetime.now(timezone.utc).isoformat(),
        ),
    )

    loader = WarehouseLoader(repo, store)
    plan = loader.run()

    assert len(plan.load) == 1
    assert len(plan.replace) == 1
    assert len(plan.demote) == 1

    pointers = {(
        p.source,
        p.customer_id,
        p.query_name,
        p.logical_date,
    ): p for p in store.list_pointers()}

    assert ("google_ads", "123", "campaign_stats", "2024-01-01") in pointers
    assert pointers[
        ("google_ads", "123", "campaign_stats", "2024-01-01")
    ].run_id == "run-load"

    assert ("google_ads", "123", "campaign_stats", "2024-01-02") in pointers
    assert pointers[
        ("google_ads", "123", "campaign_stats", "2024-01-02")
    ].run_id == "run-new"

    assert ("google_ads", "123", "campaign_stats", "2024-01-03") not in pointers
