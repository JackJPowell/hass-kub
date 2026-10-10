"""Bound routine polling without losing month-to-date totals or retaining history."""

import asyncio
from datetime import datetime
from urllib.parse import parse_qs, urlparse

import pytest
from kub import kub_utilities as ku


class FakeResponse:
    async def json(self):
        return {
            "usage-value": [
                {"readDateTime": "2026-03-01T00:00:00", "usageValuesChildren": [1]},
                {
                    "id": "hour",
                    "readDateTime": "2026-03-01T01:00:00",
                    "usageValuesChildren": [],
                },
            ],
            "usage-aggregate": [{}, {"readValue": 2.0, "uom": "KWH", "cost": 0.2}],
        }


class FakeHttp:
    def __init__(self, *args, **kwargs):
        self.urls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def fetch(self, url):
        self.urls.append(url)
        return FakeResponse()


def configured_api(monkeypatch, today):
    class FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return today.replace(tzinfo=tz)

    monkeypatch.setattr(ku, "datetime", FrozenDatetime)
    http = FakeHttp()
    monkeypatch.setattr(ku, "Http", lambda *args, **kwargs: http)
    api = ku.KubUtility("user", "password")
    api.person_id = "P1"
    api.service_list = ["electricity"]
    api.account = {"electricity": {"id": "SP-1", "utility": "electricity"}}
    api.usage = {"electricity": {"2025-01-01": {"stale": {}}}}
    api.monthly_total = {"electricity": {}}

    async def ensure_token():
        pass

    api._ensure_token = ensure_token
    return api, http


@pytest.mark.parametrize(
    ("today", "expected_start"),
    [
        (datetime(2026, 3, 1, tzinfo=ku._TZ_LOCAL), "2026-02-22"),
        (datetime(2026, 3, 31, tzinfo=ku._TZ_LOCAL), "2026-03-01"),
        (datetime(2026, 1, 2, tzinfo=ku._TZ_LOCAL), "2025-12-26"),
    ],
)
def test_recent_fetch_covers_month_and_overlap(monkeypatch, today, expected_start):
    api, http = configured_api(monkeypatch, today)
    usage = asyncio.run(api.retrieve_recent_usage())
    query = parse_qs(urlparse(http.urls[0]).query)
    assert query["startDate"] == [expected_start]
    assert query["endDate"] == [today.date().isoformat()]
    assert "2025-01-01" not in usage["electricity"]
    if today.month == 3:
        assert api.monthly_total["electricity"] == {"usage": 2.0, "cost": 0.2}


def test_explicit_start_extends_window_for_downtime(monkeypatch):
    api, http = configured_api(monkeypatch, datetime(2026, 3, 31, tzinfo=ku._TZ_LOCAL))
    asyncio.run(api.retrieve_recent_usage(start_date="2026-01-15"))
    assert parse_qs(urlparse(http.urls[0]).query)["startDate"] == ["2026-01-15"]


def test_invalid_overlap_does_not_request_data(monkeypatch):
    api, http = configured_api(monkeypatch, datetime(2026, 3, 31, tzinfo=ku._TZ_LOCAL))
    with pytest.raises(ValueError):
        asyncio.run(api.retrieve_recent_usage(days=0))
    assert http.urls == []


def test_failed_request_keeps_previous_snapshot(monkeypatch):
    api, http = configured_api(monkeypatch, datetime(2026, 3, 31, tzinfo=ku._TZ_LOCAL))

    async def fail(url):
        raise RuntimeError("connection lost")

    http.fetch = fail
    with pytest.raises(RuntimeError):
        asyncio.run(api.retrieve_recent_usage())
    assert "2025-01-01" in api.usage["electricity"]
    assert api.http is None
