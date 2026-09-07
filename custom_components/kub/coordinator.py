"""The KUB integration coordinator."""

from __future__ import annotations

import datetime
import logging
from typing import Any
from zoneinfo import ZoneInfo

from homeassistant import config_entries
from homeassistant.components.recorder.models import (
    StatisticData,
    StatisticMeanType,
    StatisticMetaData,
)
from homeassistant.components.recorder.statistics import async_import_statistics
from homeassistant.const import UnitOfEnergy, UnitOfVolume
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from kub import kub_utilities

from .const import CONF_WATER_STATISTICS, DEVICE_SCAN_INTERVAL, DOMAIN
from .helpers import get_service_utility
from .repairs import (
    async_create_authentication_issue,
    async_delete_authentication_issue,
)

_LOGGER = logging.getLogger(__name__)

_TZ_LOCAL = ZoneInfo("America/New_York")


class KUBCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Data update coordinator for KUB."""

    def __init__(self, hass: HomeAssistant, api: kub_utilities.KubUtility) -> None:
        """Initialize the Coordinator."""
        super().__init__(
            hass,
            name=DOMAIN,
            logger=_LOGGER,
            update_interval=DEVICE_SCAN_INTERVAL,
        )

        self.hass = hass
        self.config_entry = config_entries.current_entry.get()
        self.entities = []
        self.api = api
        self.username = api.username
        self.password = api.password
        self.account = api.account
        self.data = {
            "usage": {},
            "current_electricity": {},
            "current_gas": {},
            "current_water": {},
            "current_wastewater": {},
            "services": {},
            "service_list": [],
            "monthly_total": {
                "electricity": {"usage": None, "cost": None},
                "gas": {"usage": None, "cost": None},
                "water": {"usage": None, "cost": None},
                "wastewater": {"usage": None, "cost": None},
            },
        }

    async def _async_update_data(self) -> dict[str, Any]:
        """Get the latest data from KUB."""
        try:
            self.data["usage"] = await self.api.retrieve_last_year()
            self.data["monthly_total"] = self.api.monthly_total
            self.data["services"] = self.api.services
            self.data["service_list"] = self.api.service_list
            # KUB delays and revises recent hourly data; reconcile stable history.
            await self._insert_statistics()
            async_delete_authentication_issue(self.hass, self.config_entry)
            return self.data
        except kub_utilities.KUBAuthenticationError as error:
            async_create_authentication_issue(self.hass, self.config_entry)
            raise ConfigEntryAuthFailed(error) from error
        except Exception as ex:
            raise UpdateFailed(f"Error communicating with the KUB api {ex}") from ex

    async def _insert_statistics(self) -> None:
        """Reconcile KUB's complete hourly data with recorder statistics.

        ``async_import_statistics`` updates an existing row when its statistic
        id and start time match. Re-importing the stable portion of KUB's
        history therefore corrects late revisions and fills holes without
        creating duplicate rows. KUB data for today and yesterday is excluded
        because it is routinely incomplete or revised.
        """
        latest_complete_date = datetime.datetime.now(
            _TZ_LOCAL
        ).date() - datetime.timedelta(days=2)

        for service_key, utility_data in self.data["usage"].items():
            utility = get_service_utility(self.account, service_key)
            cost_statistic_id = f"sensor.kub_{service_key}_cost"
            consumption_statistic_id = f"sensor.kub_{service_key}_consumption"
            cost_statistics = []
            consumption_statistics = []
            cost_sum = 0.0
            consumption_sum = 0.0

            for date in sorted(utility_data):
                if datetime.date.fromisoformat(date) > latest_complete_date:
                    continue
                day = utility_data[date]
                if len(day) < 20:
                    continue
                for time in sorted(day):
                    hour = day[time]
                    start = datetime.datetime.fromisoformat(
                        hour["readDateTime"]
                    ).replace(tzinfo=_TZ_LOCAL)
                    hour_cost = hour.get("cost") or 0.0
                    hour_usage = hour.get("utilityUsed") or 0.0
                    if (
                        utility == kub_utilities.KUBUtilityTypes.WATER.name.lower()
                        and self.config_entry.options.get(CONF_WATER_STATISTICS, False)
                    ):
                        hour_cost *= 2
                        hour_usage *= 2
                    # A year is re-imported as one coherent series. This makes
                    # existing rows for the same hour update atomically and
                    # replaces prior bad cumulative sums with KUB-derived ones.
                    cost_sum += hour_cost
                    consumption_sum += hour_usage
                    cost_statistics.append(
                        StatisticData(start=start, state=hour_cost, sum=cost_sum)
                    )
                    consumption_statistics.append(
                        StatisticData(
                            start=start, state=hour_usage, sum=consumption_sum
                        )
                    )

            name_prefix = f"KUB {utility.capitalize()}"
            cost_metadata = StatisticMetaData(
                mean_type=StatisticMeanType.NONE,
                has_sum=True,
                name=f"{name_prefix} Cost",
                source="recorder",
                statistic_id=cost_statistic_id,
                unit_of_measurement="USD",
                unit_class=None,
            )
            if utility == kub_utilities.KUBUtilityTypes.ELECTRICITY.name.lower():
                unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
                unit_class = "energy"
            elif utility == kub_utilities.KUBUtilityTypes.GAS.name.lower():
                unit_of_measurement = UnitOfVolume.CENTUM_CUBIC_FEET
                unit_class = "volume"
            else:
                unit_of_measurement = UnitOfVolume.CUBIC_FEET
                unit_class = "volume"
            consumption_metadata = StatisticMetaData(
                mean_type=StatisticMeanType.NONE,
                has_sum=True,
                name=f"{name_prefix} Consumption",
                source="recorder",
                statistic_id=consumption_statistic_id,
                unit_of_measurement=unit_of_measurement,
                unit_class=unit_class,
            )
            if cost_statistics:
                async_import_statistics(self.hass, cost_metadata, cost_statistics)
            if consumption_statistics:
                async_import_statistics(
                    self.hass, consumption_metadata, consumption_statistics
                )
