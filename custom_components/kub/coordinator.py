"""The IntelliFire integration."""

from __future__ import annotations

import datetime
import logging
from typing import Any
from zoneinfo import ZoneInfo

from homeassistant import config_entries
from homeassistant.components.recorder.models import StatisticData, StatisticMetaData
from homeassistant.components.recorder.statistics import async_import_statistics
from homeassistant.const import UnitOfEnergy, UnitOfVolume
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from kub import kub_utilities

from .const import CONF_WATER_STATISTICS, DEVICE_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)


class KUBCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Data update coordinator for KUB."""

    def __init__(self, hass: HomeAssistant, api: kub_utilities.kubUtility) -> None:
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
            self.data["usage"] = await self.api.retrieve_last_31_days()
            self.data["monthly_total"] = self.api.monthly_total
            self.data["services"] = self.api.services
            self.data["service_list"] = self.api.service_list
            # Because KUB provides historical usage/cost with a delay of approximately one day
            # we need to insert data into statistics.
            await self._insert_statistics()
            return self.data
        except kub_utilities.KUBAuthenticationError as error:
            raise ConfigEntryAuthFailed(error) from error
        except Exception as ex:
            raise UpdateFailed(f"Error communicating with the KUB api {ex}") from ex

    async def _insert_statistics(self) -> None:
        """Insert KUB statistics."""
        for utility in self.data["usage"]:
            utility_data = self.data["usage"][utility]
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
                # Skip loading statistics that don't have a full days worth of data
                # We will populate this day on the next pass
                # HA displays errors in utility usage if partial day stats are added
                if len(day) < 20:
                    continue
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

                    # If we are processing water and user has selected to include
                    # waste water, double count usage as KUB does. This is not
                    # sufficient for residences with separate waste water meters.
                    # Please help if this is you!
                    if (
                        utility.lower()
                        == kub_utilities.KUBUtilityTypes.WATER.name.lower()
                        and self.config_entry.options.get(CONF_WATER_STATISTICS, False)
                        is True
                    ):
                        cost_sum += hour.get("cost")
                        consumption_sum += hour.get("utilityUsed")

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

            if (
                utility.lower()
                == kub_utilities.KUBUtilityTypes.ELECTRICITY.name.lower()
            ):
                unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
            elif utility.lower() == kub_utilities.KUBUtilityTypes.GAS.name.lower():
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
