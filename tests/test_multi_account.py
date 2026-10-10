"""Service discovery across several KUB accounts, with a faked HTTP layer.

Run with: pip install pytest aiohttp && pytest tests
The library module is loaded by path so Home Assistant does not need to be installed.
"""

import asyncio
import importlib.util
import sys
from pathlib import Path

import aiohttp
import pytest

_LIB = Path(__file__).parents[1] / "custom_components/kub/kub/kub_utilities.py"
_spec = importlib.util.spec_from_file_location("kub_utilities", _LIB)
ku = importlib.util.module_from_spec(_spec)
sys.modules["kub_utilities"] = ku
_spec.loader.exec_module(ku)


def service_point(service_id, service_type="E-RES"):
    return {"id": service_id, "type": service_type}


class FakeResponse:
    def __init__(self, data):
        self._data = data

    async def json(self):
        return self._data


class FakeHttp:
    """Answers any URL containing a route fragment; an int means that HTTP status."""

    def __init__(self, routes):
        self.routes = routes
        self.urls = []

    async def fetch(self, url):
        self.urls.append(url)
        for fragment, value in self.routes.items():
            if fragment in url:
                if isinstance(value, int):
                    raise aiohttp.ClientResponseError(None, (), status=value)
                return FakeResponse(value)
        raise AssertionError(f"unexpected request: {url}")


def load(routes):
    api = ku.KubUtility("user", "password")
    api.http = FakeHttp(routes)
    asyncio.run(api._retrieve_account_info())
    return api


LOGIN = {"person": [{"id": "P1", "accounts": ["ACCT-A", "ACCT-B"]}]}
ACCOUNT_A = {"service-point": [service_point("SP-1")]}
ACCOUNT_B = {"service-point": [service_point("SP-2"), service_point("SP-3")]}


def test_every_account_is_read():
    api = load({"users/user": LOGIN, "accounts/ACCT-A": ACCOUNT_A, "accounts/ACCT-B": ACCOUNT_B})
    assert api.service_list == ["electricity_SP-1", "electricity_SP-2", "electricity_SP-3"]
    assert api.account["electricity_SP-1"]["account_id"] == "ACCT-A"
    assert api.account["electricity_SP-3"]["account_id"] == "ACCT-B"


def test_each_service_keeps_the_person_that_owns_its_account():
    login = {
        "person": [
            {"id": "P1", "accounts": ["ACCT-A"]},
            {"id": "P2", "accounts": ["ACCT-B"]},
        ]
    }
    api = load({"users/user": login, "accounts/ACCT-A": ACCOUNT_A, "accounts/ACCT-B": ACCOUNT_B})
    assert api.account["electricity_SP-1"]["person_id"] == "P1"
    assert api.account["electricity_SP-2"]["person_id"] == "P2"


def test_single_meter_keeps_the_plain_utility_key():
    login = {"person": [{"id": "P1", "accounts": ["ACCT-A"]}]}
    api = load({"users/user": login, "accounts/ACCT-A": ACCOUNT_A})
    assert api.service_list == ["electricity"]


def test_water_and_sewer_share_one_service_point():
    login = {"person": [{"id": "P1", "accounts": ["ACCT-A"]}]}
    api = load({"users/user": login, "accounts/ACCT-A": {"service-point": [service_point("SP-9", "W/S-RES")]}})
    assert api.service_list == ["water", "wastewater"]
    assert api.account["water"]["id"] == api.account["wastewater"]["id"] == "SP-9"


def test_unsupported_service_type_is_skipped_not_fatal():
    login = {"person": [{"id": "P1", "accounts": ["ACCT-A"]}]}
    points = {"service-point": [service_point("SP-1"), service_point("SP-7", "LIGHTING")]}
    api = load({"users/user": login, "accounts/ACCT-A": points})
    assert api.service_list == ["electricity"]


def test_extra_account_that_fails_is_skipped():
    api = load({"users/user": LOGIN, "accounts/ACCT-A": ACCOUNT_A, "accounts/ACCT-B": 404})
    assert api.service_list == ["electricity"]


@pytest.mark.parametrize(
    "routes",
    [
        {"users/user": LOGIN, "accounts/ACCT-A": 500, "accounts/ACCT-B": ACCOUNT_B},  # first account
        {"users/user": LOGIN, "accounts/ACCT-A": ACCOUNT_A, "accounts/ACCT-B": 401},  # lost login
    ],
)
def test_fatal_failures_still_propagate(routes):
    with pytest.raises(aiohttp.ClientResponseError):
        load(routes)


def test_refreshing_does_not_accumulate_state():
    api = load({"users/user": LOGIN, "accounts/ACCT-A": ACCOUNT_A, "accounts/ACCT-B": ACCOUNT_B})
    asyncio.run(api._retrieve_services())
    assert len(api.service_list) == 3 and len(api.account) == 3


def test_usage_request_uses_the_owning_persons_id():
    api = ku.KubUtility("user", "password")
    api.person_id = "P1"
    api.account = {"electricity": {"id": "SP-1", "utility": "electricity", "person_id": "P2"}}
    api.usage = {"electricity": {}}
    api.monthly_total = {"electricity": {}}
    api.http = FakeHttp({"usage-values": {"usage-value": [], "usage-aggregate": []}})
    asyncio.run(api._retrieve_usage("electricity", start_date="2026-01-01"))
    assert "personId=P2" in api.http.urls[0] and "servicePointId=SP-1" in api.http.urls[0]
