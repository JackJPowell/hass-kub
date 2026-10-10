"""Service discovery across several KUB accounts, with a faked HTTP layer.

Run with: pip install pytest kub==0.8.1 && pytest tests
Exercise the published package used by Home Assistant.
"""

import asyncio

import aiohttp
import pytest
from kub import kub_utilities as ku


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
    assert api.service_list == ["electricity", "electricity_SP-2", "electricity_SP-3"]
    assert api.account["electricity"]["account_id"] == "ACCT-A"
    assert api.account["electricity_SP-3"]["account_id"] == "ACCT-B"


def test_each_service_keeps_the_person_that_owns_its_account():
    login = {
        "person": [
            {"id": "P1", "accounts": ["ACCT-A"]},
            {"id": "P2", "accounts": ["ACCT-B"]},
        ]
    }
    api = load({"users/user": login, "accounts/ACCT-A": ACCOUNT_A, "accounts/ACCT-B": ACCOUNT_B})
    assert api.account["electricity"]["person_id"] == "P1"
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


def test_upgrade_preserves_the_first_accounts_existing_meter_key():
    first_only = {"person": [{"id": "P1", "accounts": ["ACCT-A"]}]}
    old = load({"users/user": first_only, "accounts/ACCT-A": ACCOUNT_A})
    upgraded = load({"users/user": LOGIN, "accounts/ACCT-A": ACCOUNT_A, "accounts/ACCT-B": ACCOUNT_B})
    assert old.account["electricity"]["id"] == upgraded.account["electricity"]["id"]
    # Both sensor unique ids and external statistic ids are derived from this key.
    assert upgraded.service_list[0] == old.service_list[0] == "electricity"


def test_first_account_with_multiple_meters_keeps_existing_suffixed_keys():
    first_only = {"person": [{"id": "P1", "accounts": ["ACCT-A"]}]}
    first_meters = {"service-point": [service_point("SP-1"), service_point("SP-4")]}
    old = load({"users/user": first_only, "accounts/ACCT-A": first_meters})
    upgraded = load({"users/user": LOGIN, "accounts/ACCT-A": first_meters, "accounts/ACCT-B": ACCOUNT_B})
    assert old.service_list == ["electricity_SP-1", "electricity_SP-4"]
    assert upgraded.service_list[:2] == old.service_list


def test_extra_account_failure_and_recovery_do_not_rename_primary_meter():
    api = load({"users/user": LOGIN, "accounts/ACCT-A": ACCOUNT_A, "accounts/ACCT-B": ACCOUNT_B})
    api.http.routes["accounts/ACCT-B"] = 500
    asyncio.run(api._retrieve_services())
    assert api.service_list == ["electricity"]
    assert api.account["electricity"]["id"] == "SP-1"
    api.http.routes["accounts/ACCT-B"] = ACCOUNT_B
    asyncio.run(api._retrieve_services())
    assert api.service_list == ["electricity", "electricity_SP-2", "electricity_SP-3"]


def test_failed_extra_account_at_startup_does_not_rename_other_extra_meters():
    login = {"person": [{"id": "P1", "accounts": ["ACCT-A", "ACCT-B", "ACCT-C"]}]}
    routes = {
        "users/user": login,
        "accounts/ACCT-A": {"service-point": [service_point("SP-1", "G-RES")]},
        "accounts/ACCT-B": {"service-point": [service_point("SP-2")]},
        "accounts/ACCT-C": {"service-point": [service_point("SP-3")]},
    }
    healthy = load(routes)
    failed = load({**routes, "accounts/ACCT-C": 500})
    assert "electricity_SP-2" in healthy.account
    assert "electricity_SP-2" in failed.account
    assert "electricity" not in failed.account


def test_extra_account_with_unique_utility_does_not_claim_legacy_key():
    api = load({
        "users/user": LOGIN,
        "accounts/ACCT-A": ACCOUNT_A,
        "accounts/ACCT-B": {"service-point": [service_point("SP-9", "G-RES")]},
    })
    assert api.service_list == ["electricity", "gas_SP-9"]


def test_empty_login_has_a_clear_error():
    with pytest.raises(ValueError, match="No KUB accounts found"):
        load({"users/user": {"person": []}})


def test_first_person_without_accounts_uses_the_actual_account_owner():
    login = {"person": [
        {"id": "P0", "accounts": []},
        {"id": "P1", "accounts": ["ACCT-A"]},
    ]}
    api = load({"users/user": login, "accounts/ACCT-A": ACCOUNT_A})
    assert api.person_id == "P1"
    assert api.account["electricity"]["person_id"] == "P1"


def test_refresh_removes_stale_meter_caches_and_retains_current_usage():
    api = load({"users/user": LOGIN, "accounts/ACCT-A": ACCOUNT_A, "accounts/ACCT-B": ACCOUNT_B})
    api.usage["electricity"] = {"2026-03-01": {}}
    api.monthly_total["electricity"] = {"usage": 2.0, "cost": 0.2}
    api.http.routes["accounts/ACCT-B"] = 404
    asyncio.run(api._retrieve_services())
    assert api.usage == {"electricity": {"2026-03-01": {}}}
    assert api.monthly_total == {"electricity": {"usage": 2.0, "cost": 0.2}}
