"""The KUB integration coordinator."""

from __future__ import annotations

import datetime
import logging
from typing import Any
from zoneinfo import ZoneInfo

from homeassistant import config_entries
from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.models import (StatisticData,
                                                      StatisticMeanType,
                                                      StatisticMetaData)
from homeassistant.components.recorder.statistics import (
    async_import_statistics,
    get_last_statistics,
)
from homeassistant.const import UnitOfEnergy, UnitOfVolume
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import (DataUpdateCoordinator,
                                                      UpdateFailed)
from kub import kub_utilities

from .const import CONF_WATER_STATISTICS, DEVICE_SCAN_INTERVAL, DOMAIN

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
            raise UpdateFailed(
                f"Error communicating with the KUB api {ex}") from ex

    async def _get_last_stat_sum_and_time(
        self, statistic_id: str
    ) -> tuple[float, float]:
        """Return (last_sum, last_start_timestamp) for a statistic, or (0.0, 0) if none."""
        stats = await get_instance(self.hass).async_add_executor_job(
            get_last_statistics, self.hass, 1, statistic_id, True, {"sum"}
        )
        records = stats.get(statistic_id)
        if not records:
            _LOGGER.debug(
                "No existing statistics found for %s; starting sum from 0",
                statistic_id,
            )
            return 0.0, 0
        record = records[0]
        last_sum = record.get("sum") or 0.0
        start = record.get("start")
        if start is None:
            last_ts = 0
        elif hasattr(start, "timestamp"):
            last_ts = start.timestamp()
        else:
            last_ts = float(start)
        _LOGGER.debug(
            "Last recorded stat for %s: sum=%.4f at %s",
            statistic_id,
            last_sum,
            start,
        )
        return last_sum, last_ts

    async def _insert_statistics(self) -> None:
        """Insert KUB statistics.

        Fetches the last recorded sum for each statistic before accumulating
        new data so that the running total is truly monotonically increasing
        across billing-period boundaries.  Only data points newer than the
        most recently stored statistic are appended, preventing the
        zero-reset cliff that previously appeared on the Energy Dashboard.
        """
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
            cost_statistics = []
            consumption_statistics = []

            # Seed running totals from the last recorded statistics so that
            # the cumulative sum never resets to zero at a billing-period
            # boundary.  last_stats_time gates insertion to only new data.
            cost_sum, _ = await self._get_last_stat_sum_and_time(cost_statistic_id)
            consumption_sum, last_stats_time = await self._get_last_stat_sum_and_time(
                consumption_statistic_id
            )
            _LOGGER.debug(
                "%s: seeded cost_sum=%.4f consumption_sum=%.4f last_stats_time=%s",
                utility,
                cost_sum,
                consumption_sum,
                datetime.datetime.fromtimestamp(last_stats_time, tz=_TZ_LOCAL)
                if last_stats_time
                else "none",
            )

            for date in sorted(cost_reads):
                day = cost_reads[date]
                # Skip loading statistics that don't have a full days worth of data
                # We will populate this day on the next pass
                # HA displays errors in utility usage if partial day stats are added
                if len(day) < 20:
                    continue
                for time in sorted(day):
                    hour = day[time]
                    timestamp = hour.get("readDateTime")
                    naive_datetime = datetime.datetime.fromisoformat(timestamp)
                    start = naive_datetime.replace(tzinfo=_TZ_LOCAL)

                    if start.timestamp() <= last_stats_time:
                        continue

                    hour_cost = hour.get("cost") or 0.0
                    hour_usage = hour.get("utilityUsed") or 0.0

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
                        cost_sum += hour_cost
                        consumption_sum += hour_usage

                    cost_sum += hour_cost
                    consumption_sum += hour_usage

                    cost_statistics.append(
                        StatisticData(start=start, state=hour_cost, sum=cost_sum)
                    )
                    consumption_statistics.append(
                        StatisticData(
                            start=start,
                            state=hour_usage,
                            sum=consumption_sum,
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

            if (
                utility.lower()
                == kub_utilities.KUBUtilityTypes.ELECTRICITY.name.lower()
            ):
                unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
                unit_class = "energy"
            elif utility.lower() == kub_utilities.KUBUtilityTypes.GAS.name.lower():
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
                _LOGGER.debug(
                    "%s: inserting %d cost and %d consumption stat entries",
                    utility,
                    len(cost_statistics),
                    len(consumption_statistics),
                )
                async_import_statistics(self.hass, cost_metadata, cost_statistics)
            if consumption_statistics:
                async_import_statistics(
                    self.hass, consumption_metadata, consumption_statistics
                )
            if not cost_statistics and not consumption_statistics:
                _LOGGER.debug(
                    "%s: no new stat entries to insert (all data already recorded)",
                    utility,
                )
