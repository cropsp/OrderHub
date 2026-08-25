"""BUG-9 — scheduler consumes the IMP-2 ImportResult shape from sync_shop_orders.

The scheduler used to read an int (`count > 0`); after IMP-2,
sync_shop_orders returns ImportResult. These tests pin the post-fix
contract: success log line, optional catalog-counter suffix, per-order
error warning, silence on idle.

Mocks scheduler.sync_shop_orders + scheduler.async_session_factory; no
real DB or HTTP.
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from schemas.common import ImportResult


def _make_db_with_one_shop(shop, system_user):
    """Build an AsyncMock DB session whose two execute() calls return
    the System user and a single-shop list, in scheduler call order."""
    user_result = MagicMock()
    user_result.scalar_one_or_none = MagicMock(return_value=system_user)

    shops_result = MagicMock()
    shops_scalars = MagicMock()
    shops_scalars.all = MagicMock(return_value=[shop])
    shops_result.scalars = MagicMock(return_value=shops_scalars)

    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[user_result, shops_result])
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    return db


def _session_factory_returning(db):
    """Build a sync MagicMock that, when called, returns an async
    context manager yielding `db`."""
    factory = MagicMock()
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=db)
    cm.__aexit__ = AsyncMock(return_value=None)
    factory.return_value = cm
    return factory


@pytest.mark.asyncio
async def test_run_shopify_sync_logs_success_with_catalog_counters(caplog):
    shop = MagicMock(id=uuid4())
    shop.name = "MyShop"
    system_user = MagicMock()
    db = _make_db_with_one_shop(shop, system_user)

    with patch("scheduler.async_session_factory", _session_factory_returning(db)), \
         patch("scheduler.sync_shop_orders", new_callable=AsyncMock) as mock_sync:
        mock_sync.return_value = ImportResult(
            imported=2,
            skipped=0,
            errors=[],
            products_created=1,
            variants_created=3,
        )

        from scheduler import run_shopify_sync
        with caplog.at_level("INFO", logger="scheduler"):
            await run_shopify_sync()

    info_msgs = [r.getMessage() for r in caplog.records if r.levelname == "INFO"]
    assert any(
        "Synced 2 orders for shop MyShop" in m
        and "+1 product" in m
        and "+3 variants" in m
        for m in info_msgs
    ), info_msgs
    db.commit.assert_awaited_once()
    db.rollback.assert_not_called()


@pytest.mark.asyncio
async def test_run_shopify_sync_logs_warning_on_per_order_errors(caplog):
    shop = MagicMock(id=uuid4())
    shop.name = "MyShop"
    system_user = MagicMock()
    db = _make_db_with_one_shop(shop, system_user)

    with patch("scheduler.async_session_factory", _session_factory_returning(db)), \
         patch("scheduler.sync_shop_orders", new_callable=AsyncMock) as mock_sync:
        mock_sync.return_value = ImportResult(
            imported=1,
            skipped=0,
            errors=[{"external_id": "X", "error": "boom"}],
            products_created=0,
            variants_created=0,
        )

        from scheduler import run_shopify_sync
        with caplog.at_level("INFO", logger="scheduler"):
            await run_shopify_sync()

    info_msgs = [r.getMessage() for r in caplog.records if r.levelname == "INFO"]
    warn_msgs = [r.getMessage() for r in caplog.records if r.levelname == "WARNING"]

    # Partial success: success line still emitted, no catalog suffix.
    assert any(
        "Synced 1 orders for shop MyShop" in m and "(" not in m
        for m in info_msgs
    ), info_msgs
    # Per-order errors surfaced as warning naming shop + error count.
    assert any(
        "MyShop" in m and "1 per-order error" in m
        for m in warn_msgs
    ), warn_msgs
    db.commit.assert_awaited_once()
    db.rollback.assert_not_called()


@pytest.mark.asyncio
async def test_run_shopify_sync_silent_on_zero_imported(caplog):
    shop = MagicMock(id=uuid4())
    shop.name = "MyShop"
    system_user = MagicMock()
    db = _make_db_with_one_shop(shop, system_user)

    with patch("scheduler.async_session_factory", _session_factory_returning(db)), \
         patch("scheduler.sync_shop_orders", new_callable=AsyncMock) as mock_sync:
        mock_sync.return_value = ImportResult(
            imported=0,
            skipped=0,
            errors=[],
            products_created=0,
            variants_created=0,
        )

        from scheduler import run_shopify_sync
        with caplog.at_level("INFO", logger="scheduler"):
            await run_shopify_sync()

    scheduler_records = [r for r in caplog.records if r.name == "scheduler"]
    assert not any("Synced" in r.getMessage() for r in scheduler_records)
    assert not any(r.levelname == "WARNING" for r in scheduler_records)
    db.commit.assert_awaited_once()
    db.rollback.assert_not_called()


# ── Startup-fire completeness guard ────────────────────────
#
# The same defect shipped twice in two days: run_wb_tracking_poll (fixed in
# 086e713) and run_shopify_refund_sync were both registered as daily 'interval'
# jobs with no next_run_time, so every backend restart deferred them another 24
# hours. Two instances is a pattern, so this guard forces the question to be
# answered for every job — the way test_route_scope_completeness.py and
# test_money_field_completeness.py force a verdict on new routes and money fields.
#
# It deliberately does NOT require a startup fire. A daily job may have good
# reason to wait out its first interval; it just has to say so.
#
#   startup:<reason>  → registered with next_run_time; fires once at boot.
#   deferred:<reason> → deliberately waits a full interval before its first run.
#
# A new job FAILS here until classified, a removed job FAILS as stale, and a
# verdict that disagrees with the actual registration FAILS too — so the list
# cannot quietly drift away from the code.
STARTUP_POLICY: dict[str, str] = {
    "run_shopify_sync": "deferred: 15-min interval, a boot fire would save 15 min",
    "run_westernbid_poll": "deferred: 15-min interval, same as the order sync",
    "run_shopify_refund_sync": (
        "startup: daily; a re-run is one paginated Shopify read and zero writes "
        "(refund ids pre-loaded and skipped, insert is ON CONFLICT DO NOTHING)"
    ),
    "run_wb_tracking_poll": (
        "startup: 4-hourly; one batched keyless request, and record_poll writes "
        "an event only on an observed change"
    ),
    "run_fx_rate_refresh": (
        "startup: daily; FX_MIN_REFETCH_HOURS inside the job bounds the re-fetch"
    ),
}


class _RecordingScheduler:
    """Stands in for AsyncIOScheduler: records add_job calls, never starts."""

    def __init__(self, *args, **kwargs):
        self.jobs: list[tuple] = []

    def add_job(self, func, trigger=None, **kwargs):
        self.jobs.append((func, trigger, kwargs))

    def start(self):
        pass


def _registered_jobs() -> dict[str, dict]:
    """Job name -> add_job kwargs, without starting a real scheduler."""
    recorder = _RecordingScheduler()
    with patch("scheduler.AsyncIOScheduler", return_value=recorder):
        from scheduler import start_scheduler
        start_scheduler()
    return {func.__name__: kwargs for func, _trigger, kwargs in recorder.jobs}


def test_every_scheduled_job_declares_a_startup_verdict():
    jobs = _registered_jobs()
    assert jobs, "start_scheduler registered no jobs — the recorder patch broke"

    unclassified = sorted(set(jobs) - set(STARTUP_POLICY))
    assert not unclassified, (
        f"Scheduled job(s) with no startup verdict: {unclassified}. "
        "Add 'startup:<reason>' (register it with next_run_time so it fires at "
        "boot) or 'deferred:<reason>' (it deliberately waits a full interval) to "
        "STARTUP_POLICY."
    )

    stale = sorted(set(STARTUP_POLICY) - set(jobs))
    assert not stale, f"STARTUP_POLICY lists jobs that are no longer registered: {stale}"


def test_startup_verdicts_match_the_actual_registration():
    jobs = _registered_jobs()
    mismatched = []
    for name, verdict in STARTUP_POLICY.items():
        if name not in jobs:
            continue  # covered by the staleness assertion above
        fires_at_startup = jobs[name].get("next_run_time") is not None
        if verdict.startswith("startup:") and not fires_at_startup:
            mismatched.append(f"{name}: declared 'startup' but has no next_run_time")
        elif verdict.startswith("deferred:") and fires_at_startup:
            mismatched.append(f"{name}: declared 'deferred' but sets next_run_time")
    assert not mismatched, "STARTUP_POLICY disagrees with the code: " + "; ".join(mismatched)


def test_startup_verdicts_carry_a_reason():
    """'deferred:' alone must not be a way to dodge the question."""
    bad = []
    for name, verdict in STARTUP_POLICY.items():
        prefix, _, reason = verdict.partition(":")
        if prefix not in {"startup", "deferred"}:
            bad.append(f"{name}: verdict must start with 'startup:' or 'deferred:'")
        elif not reason.strip():
            bad.append(f"{name}: verdict gives no reason")
    assert not bad, "; ".join(bad)
