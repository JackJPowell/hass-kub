"""Verify the installed dependency and real Home Assistant statistics API."""

import asyncio
import importlib
import json
from datetime import datetime, timedelta
from importlib.metadata import version
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from kub import kub_utilities

pytest.importorskip("homeassistant")
integration = importlib.import_module("custom_components.kub")
coordinator = importlib.import_module("custom_components.kub.coordinator")
config_flow = importlib.import_module("custom_components.kub.config_flow")
sensor = importlib.import_module("custom_components.kub.sensor")
recorder_statistics = importlib.import_module(
    "homeassistant.components.recorder.statistics"
)
sensor_recorder = importlib.import_module("homeassistant.components.sensor.recorder")
ha_core = importlib.import_module("homeassistant.core")

ROOT = Path(__file__).parents[1]
TZ = ZoneInfo("America/New_York")


def test_runtime_imports_the_pinned_published_package():
    manifest = json.loads((ROOT / "custom_components/kub/manifest.json").read_text())
    assert manifest["requirements"] == [f"kub=={version('kub')}"]
    assert integration.kub_utilities is coordinator.kub_utilities
    assert config_flow.kub_utilities is kub_utilities
    assert coordinator.kub_utilities is kub_utilities
    bundled = ROOT / "custom_components/kub/kub/kub_utilities.py"
    assert Path(kub_utilities.__file__).resolve() != bundled.resolve()
    assert Path(kub_utilities.__file__).read_bytes() == bundled.read_bytes()


def test_summary_sensors_do_not_generate_recorder_statistics():
    fake = SimpleNamespace(
        config_entry=None,
        entities=[],
        account={"electricity": {"utility": "electricity", "id": "123"}},
    )
    assert sensor.KUBSensor(fake, "electricity").state_class is None
    assert sensor.KUBCostSensor(fake, "electricity").state_class is None


def test_all_utilities_import_through_real_external_statistics_api(monkeypatch):
    queued = []
    recorder = SimpleNamespace(
        async_import_statistics=lambda metadata, rows, table: queued.append(
            (metadata, rows)
        )
    )
    monkeypatch.setattr(recorder_statistics, "get_instance", lambda hass: recorder)
    first = datetime.now(TZ).date() - timedelta(days=7)
    midnight = datetime.combine(first, datetime.min.time())
    day = {
        str(hour): {
            "readDateTime": (midnight + timedelta(hours=hour)).isoformat(),
            "utilityUsed": 1.0,
            "cost": 0.1,
        }
        for hour in range(1, 25)
    }
    obj = coordinator.KUBCoordinator.__new__(coordinator.KUBCoordinator)
    obj.hass = None
    obj.account = {
        utility: {"utility": utility}
        for utility in ("electricity", "gas", "water", "wastewater")
    }
    obj.data = {"usage": {utility: {first.isoformat(): day} for utility in obj.account}}
    obj.config_entry = SimpleNamespace(
        options={coordinator.CONF_WATER_STATISTICS: True}
    )

    async def anchor(statistic_id, start):
        return 100.0

    obj._async_sum_before = anchor
    asyncio.run(obj._insert_statistics(first))
    assert len(queued) == 8
    for metadata, rows in queued:
        assert metadata["source"] == "kub"
        assert metadata["statistic_id"].startswith("kub:")
        assert metadata["has_sum"] is True
        assert len(rows) == 24
        assert rows[0]["start"].astimezone(TZ).date() == first
    consumption = {meta["statistic_id"]: rows for meta, rows in queued}
    assert consumption["kub:water_consumption"][-1]["sum"] == 148.0
    assert consumption["kub:electricity_consumption"][-1]["sum"] == 124.0


def test_legacy_metadata_still_warns_but_external_metadata_does_not():
    state = ha_core.State(
        "sensor.kub_electricity_consumption",
        "25",
        {
            "device_class": "energy",
            "unit_of_measurement": "kWh",
        },
    )
    metadata = {"unit_of_measurement": "kWh", "unit_class": "energy", "mean_type": 0}
    issues = []
    sensor_recorder._update_issues(
        lambda *args: issues.append(args),
        [state],
        {state.entity_id: (1, metadata)},
        {},
    )
    assert issues[0][0] == "state_class_removed"
    issues.clear()
    sensor_recorder._update_issues(
        lambda *args: issues.append(args),
        [state],
        {"kub:electricity_consumption": (1, metadata)},
        {},
    )
    assert issues == []
