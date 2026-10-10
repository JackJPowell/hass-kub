"""Exercise coordinator window selection without requiring Home Assistant."""

import ast
import asyncio
import datetime
import importlib.util
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

_COORDINATOR = Path(__file__).parents[1] / "custom_components/kub/coordinator.py"
TZ = ZoneInfo("America/New_York")


def coordinator(last_rows=None, anchor=None):
    calls = []

    def get_last_statistics(hass, count, statistic_id, convert, types):
        calls.append((statistic_id, count))
        return {statistic_id: (last_rows or {}).get(statistic_id, [])}

    def statistic_during_period(hass, first, end, statistic_id, types, units):
        calls.append((first, end, statistic_id, types))
        assert first is None
        return {"change": anchor}

    class Executor:
        async def async_add_executor_job(self, fn, *args):
            return fn(*args)

    # Load the real methods while leaving HA's integration setup out of the test.
    tree = ast.parse(_COORDINATOR.read_text())
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef))
    methods = [
        node
        for node in cls.body
        if isinstance(node, ast.AsyncFunctionDef)
        and node.name
        in {"_async_reconciliation_start", "_async_sum_before", "_insert_statistics"}
    ]
    namespace = {
        "datetime": datetime,
        "_TZ_LOCAL": TZ,
        "_RECONCILIATION_DAYS": 7,
        "DOMAIN": "kub",
        "get_instance": lambda hass: Executor(),
        "recorder_statistics": SimpleNamespace(
            get_last_statistics=get_last_statistics,
            statistic_during_period=statistic_during_period,
        ),
    }
    exec(  # noqa: S102 -- execute only repository-owned methods
        compile(ast.Module(body=methods, type_ignores=[]), str(_COORDINATOR), "exec"),
        namespace,
    )
    obj = SimpleNamespace(hass=None, api=SimpleNamespace(service_list=["electricity"]))
    return obj, namespace, calls


def test_new_series_starts_with_a_week_of_overlap():
    obj, methods, calls = coordinator()
    first = asyncio.run(methods["_async_reconciliation_start"](obj))
    assert first == datetime.datetime.now(TZ).date() - datetime.timedelta(days=7)
    assert len(calls) == 2


def test_downtime_catches_up_from_the_older_cost_or_consumption_series():
    today = datetime.datetime.now(TZ).replace(hour=0, minute=0, second=0, microsecond=0)
    obj, methods, _ = coordinator(
        last_rows={
            "kub:electricity_consumption": [
                {"start": (today - datetime.timedelta(days=20)).timestamp()}
            ],
            "kub:electricity_cost": [
                {"start": (today - datetime.timedelta(days=30)).timestamp()}
            ],
        }
    )
    assert (
        asyncio.run(methods["_async_reconciliation_start"](obj))
        == (today - datetime.timedelta(days=30)).date()
    )


def test_anchor_uses_all_prior_history_and_excludes_the_first_reimported_hour():
    obj, methods, calls = coordinator(anchor=100.0)
    start = datetime.datetime(2026, 3, 10, tzinfo=datetime.UTC)
    assert (
        asyncio.run(
            methods["_async_sum_before"](obj, "kub:electricity_consumption", start)
        )
        == 100.0
    )
    assert calls == [(None, start, "kub:electricity_consumption", {"change"})]


def test_missing_anchor_starts_at_zero():
    obj, methods, _ = coordinator()
    start = datetime.datetime(2026, 3, 10, tzinfo=datetime.UTC)
    assert (
        asyncio.run(
            methods["_async_sum_before"](obj, "kub:electricity_consumption", start)
        )
        == 0.0
    )


def test_imports_only_overlap_while_chaining_from_stored_sum():
    obj, methods, _ = coordinator(anchor=100.0)
    spec = importlib.util.spec_from_file_location(
        "window_helpers", _COORDINATOR.with_name("helpers.py")
    )
    helpers = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helpers)
    imports = {}
    methods.update(
        get_service_utility=helpers.get_service_utility,
        hourly_series=helpers.hourly_series,
        build_statistics=helpers.build_statistics,
        StatisticData=dict,
        StatisticMetaData=dict,
        StatisticMeanType=SimpleNamespace(NONE=0),
        UnitOfEnergy=SimpleNamespace(KILO_WATT_HOUR="kWh"),
        kub_utilities=SimpleNamespace(
            KUBUtilityTypes=SimpleNamespace(
                WATER=SimpleNamespace(name="WATER"),
                ELECTRICITY=SimpleNamespace(name="ELECTRICITY"),
            )
        ),
        async_add_external_statistics=lambda hass, metadata, rows: imports.update(
            {metadata["statistic_id"]: rows}
        ),
    )
    first = datetime.datetime.now(TZ).date() - datetime.timedelta(days=7)

    def day_readings(day):
        midnight = datetime.datetime.combine(day, datetime.time())
        return {
            str(hour): {
                "readDateTime": (midnight + datetime.timedelta(hours=hour)).isoformat(),
                "utilityUsed": 1.0,
                "cost": 0.1,
            }
            for hour in range(1, 25)
        }

    obj.account = {"electricity": {"utility": "electricity"}}
    obj.data = {
        "usage": {
            "electricity": {
                (first - datetime.timedelta(days=1)).isoformat(): day_readings(
                    first - datetime.timedelta(days=1)
                ),
                first.isoformat(): day_readings(first),
            }
        }
    }
    obj.config_entry = SimpleNamespace(options={})

    async def anchor(statistic_id, start):
        return await methods["_async_sum_before"](obj, statistic_id, start)

    obj._async_sum_before = anchor
    asyncio.run(methods["_insert_statistics"](obj, first))
    rows = imports["kub:electricity_consumption"]
    assert len(rows) == 24
    assert rows[0]["start"].astimezone(TZ).date() == first
    assert rows[0]["sum"] == 101.0
    assert rows[-1]["sum"] == 124.0
