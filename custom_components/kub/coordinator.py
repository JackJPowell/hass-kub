"""The IntelliFire integration."""

from __future__ import annotations

import datetime
import logging
from typing import Any
from zoneinfo import ZoneInfo

from homeassistant.components.recorder.models import StatisticData, StatisticMetaData
from homeassistant.components.recorder.statistics import async_import_statistics
from homeassistant.const import UnitOfEnergy, UnitOfVolume
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from kub import kubUtilities

from .const import DEVICE_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)


class KUBCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Data update coordinator for KUB."""

    def __init__(self, hass: HomeAssistant, api: kubUtilities.kubUtility) -> None:
        """Initialize the Coordinator."""
        super().__init__(
            hass,
            name=DOMAIN,
            logger=_LOGGER,
            update_interval=DEVICE_SCAN_INTERVAL,
        )

        self.hass = hass
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
            "monthly_total": {
                "electricity": {"usage": "", "cost": ""},
                "gas": {"usage": "", "cost": ""},
                "water": {"usage": "", "cost": ""},
            },
        }

    async def _async_update_data(self) -> dict[str, Any]:
        """Get the latest data from KUB."""
        try:
            self.data["usage"] = await self.api.retrieve_monthly_usage()
            self.data["monthly_total"] = self.api.monthly_total
            # Because KUB provides historical usage/cost with a delay of approximately one day
            # we need to insert data into statistics.
            await self._insert_statistics()
            return self.data
        except kubUtilities.KUBAuthenticationError as error:
            raise ConfigEntryAuthFailed(error) from error
        except Exception as ex:
            raise UpdateFailed(f"Error communicating with the KUB api {ex}") from ex

    async def _insert_statistics(self) -> None:
        """Insert KUB statistics."""
        for utility in self.data["usage"]:
            utility_data = self.data["usage"][utility]
            # cost_statistic_id = f"{DOMAIN}:{utility}_cost"
            # consumption_statistic_id = f"{DOMAIN}:{utility}_consumption"
            cost_statistic_id = f"sensor.kub_{utility}_cost"
            consumption_statistic_id = f"sensor.kub_{utility}_consumption"
            _LOGGER.debug(
                "Updating Statistics for %s and %s",
                cost_statistic_id,
                consumption_statistic_id,
            )

            cost_reads = utility_data
            cost_sum = 0.0
            consumption_sum = 0.0
            last_stats_time = None
            cost_statistics = []
            consumption_statistics = []

            for date in cost_reads:
                day = cost_reads[date]
                for time in day:
                    hour = day[time]
                    timestamp = hour.get("readDateTime")
                    naive_datetime = datetime.datetime.fromisoformat(timestamp)
                    timezone = ZoneInfo("EST")
                    start = naive_datetime.replace(tzinfo=timezone)
                    if (
                        last_stats_time is not None
                        and start.timestamp() <= last_stats_time
                    ):
                        continue
                    cost_sum += hour.get("cost")
                    consumption_sum += hour.get("utilityUsed")

                    cost_statistics.append(
                        StatisticData(start=start, state=hour.get("cost"), sum=cost_sum)
                    )
                    consumption_statistics.append(
                        StatisticData(
                            start=start,
                            state=hour.get("utilityUsed"),
                            sum=consumption_sum,
                        )
                    )

            name_prefix = f"KUB {utility.capitalize()}"
            cost_metadata = StatisticMetaData(
                has_mean=False,
                has_sum=True,
                name=f"{name_prefix} Cost",
                source="recorder",
                statistic_id=cost_statistic_id,
                unit_of_measurement="USD",
            )

            if utility.lower() == kubUtilities.KUBUtilityTypes.ELECTRICITY.name.lower():
                unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
            elif utility.lower() == kubUtilities.KUBUtilityTypes.GAS.name.lower():
                unit_of_measurement = UnitOfVolume.CENTUM_CUBIC_FEET
            else:
                unit_of_measurement = UnitOfVolume.CUBIC_FEET

            consumption_metadata = StatisticMetaData(
                has_mean=False,
                has_sum=True,
                name=f"{name_prefix} Consumption",
                source="recorder",
                statistic_id=consumption_statistic_id,
                unit_of_measurement=unit_of_measurement,
            )

            async_import_statistics(self.hass, cost_metadata, cost_statistics)
            async_import_statistics(
                self.hass, consumption_metadata, consumption_statistics
            )
