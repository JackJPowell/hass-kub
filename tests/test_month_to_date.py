"""Month-to-date totals must cover this year's month only.

Run with: pip install pytest aiohttp && pytest tests
"""

import asyncio
import importlib.util
import sys
from datetime import datetime, timedelta
from pathlib import Path

_LIB = Path(__file__).parents[1] / "custom_components/kub/kub/kub_utilities.py"
_spec = importlib.util.spec_from_file_location("kub_utilities", _LIB)
ku = importlib.util.module_from_spec(_spec)
sys.modules["kub_utilities"] = ku
_spec.loader.exec_module(ku)


class FakeResponse:
    def __init__(self, data):
        self._data = data

    async def json(self):
        return self._data


class FakeHttp:
    def __init__(self, data):
        self._data = data

    async def fetch(self, url):
        return FakeResponse(self._data)


def usage_response(readings):
    """Build a usage-values payload: a day header followed by one leaf per reading."""
    values = [
        {"id": "day", "readDateTime": readings[0][0].isoformat(), "usageValuesChildren": [1]}
    ]
    aggregates = [{}]
    for label, kwh in readings:
        values.append({"id": "hour", "readDateTime": label.isoformat(), "usageValuesChildren": []})
        aggregates.append({"id": "agg", "readValue": kwh, "uom": "KWH", "cost": kwh / 10, "rateDisplay": ""})
    return {"usage-value": values, "usage-aggregate": aggregates}


def month_to_date(readings):
    api = ku.KubUtility("user", "password")
    api.person_id = "P1"
    api.account = {"electricity": {"id": "SP-1", "utility": "electricity"}}
    api.usage = {"electricity": {}}
    api.monthly_total = {"electricity": {}}
    api.http = FakeHttp(usage_response(readings))
    asyncio.run(api._retrieve_usage("electricity", start_date="2025-01-01"))
    return api.monthly_total["electricity"]


def test_same_month_of_the_previous_year_is_not_counted():
    now = datetime.now()
    first = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    last_year = first.replace(year=first.year - 1)
    totals = month_to_date(
        [
            (last_year + timedelta(hours=5), 100.0),  # same month, a year ago
            (first + timedelta(hours=1), 2.0),
            (first + timedelta(hours=2), 3.0),
        ]
    )
    assert totals["usage"] == 5.0
    assert round(totals["cost"], 6) == 0.5


def test_closing_hour_of_the_previous_month_is_not_counted():
    """A label of 00:00 on the 1st closes the previous month's last hour."""
    first = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    totals = month_to_date([(first, 50.0), (first + timedelta(hours=1), 2.0)])
    assert totals["usage"] == 2.0
