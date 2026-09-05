"""Platform for sensor integration."""

import logging

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.const import UnitOfEnergy, UnitOfVolume
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import StateType

from .const import DOMAIN, KUB_COORDINATOR
from .entity import KUBEntity
from .helpers import get_service_id, get_service_utility

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, config_entry, async_add_entities):
    """Add sensors for passed config_entry in HA."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id][KUB_COORDINATOR]

    async_add_entities(
        KUBSensor(coordinator, service) for service in coordinator.account.keys()
    )

    async_add_entities(
        KUBCostSensor(coordinator, service) for service in coordinator.account.keys()
    )


class KUBSensor(KUBEntity, SensorEntity):
    """KUB Sensor Class."""

    def __init__(self, coordinator, service) -> None:
        """Initialize KUB Sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"kub_{service}_consumption"
        self.key = service
        utility = get_service_utility(coordinator.account, service)
        multiple_meters = (
            sum(
                get_service_utility(coordinator.account, service_key) == utility
                for service_key in coordinator.account
            ) > 1
        )
        meter_suffix = (
            f" ({get_service_id(coordinator.account, service)})"
            if multiple_meters
            else ""
        )
        self._attr_has_entity_name = True

        match utility:
            case "electricity":
                self._attr_device_class = SensorDeviceClass.ENERGY
                self._attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
                self._attr_name = f"Electricity Consumption{meter_suffix}"
            case "gas":
                self._attr_device_class = SensorDeviceClass.GAS
                self._attr_native_unit_of_measurement = UnitOfVolume.CENTUM_CUBIC_FEET
                self._attr_suggested_display_precision = 0
                self._attr_name = f"Gas Consumption{meter_suffix}"
            case "water":
                self._attr_device_class = SensorDeviceClass.WATER
                self._attr_native_unit_of_measurement = UnitOfVolume.CUBIC_FEET
                self._attr_suggested_display_precision = 0
                self._attr_name = f"Water Consumption{meter_suffix}"
            case "wastewater":
                self._attr_device_class = SensorDeviceClass.WATER
                self._attr_native_unit_of_measurement = UnitOfVolume.CUBIC_FEET
                self._attr_suggested_display_precision = 0
                self._attr_name = f"Waste Water Consumption{meter_suffix}"

    @property
    def available(self) -> bool:
        """Return if available."""
        return True

    @property
    def native_value(self) -> StateType:
        """Return native value for entity."""
        value = self.coordinator.data.get("monthly_total").get(self.key).get("usage")
        if value == "":
            value = None
        return value


class KUBCostSensor(KUBEntity, SensorEntity):
    """KUB Cost Sensor Class."""

    def __init__(self, coordinator, service) -> None:
        """Initialize KUB Sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"kub_{service}_cost"
        self.key = service
        utility = get_service_utility(coordinator.account, service)
        multiple_meters = (
            sum(
                get_service_utility(coordinator.account, service_key) == utility
                for service_key in coordinator.account
            ) > 1
        )
        meter_suffix = (
            f" ({get_service_id(coordinator.account, service)})"
            if multiple_meters
            else ""
        )
        self._attr_has_entity_name = True

        match utility:
            case "electricity":
                self._attr_device_class = SensorDeviceClass.MONETARY
                self._attr_native_unit_of_measurement = "USD"
                self._attr_name = f"Electricity Cost{meter_suffix}"
            case "gas":
                self._attr_device_class = SensorDeviceClass.MONETARY
                self._attr_native_unit_of_measurement = "USD"
                self._attr_suggested_display_precision = 0
                self._attr_name = f"Gas Cost{meter_suffix}"
            case "water":
                self._attr_device_class = SensorDeviceClass.MONETARY
                self._attr_native_unit_of_measurement = "USD"
                self._attr_suggested_display_precision = 0
                self._attr_name = f"Water Cost{meter_suffix}"
            case "wastewater":
                self._attr_device_class = SensorDeviceClass.MONETARY
                self._attr_native_unit_of_measurement = "USD"
                self._attr_suggested_display_precision = 0
                self._attr_name = f"Waste Water Cost{meter_suffix}"

    @property
    def available(self) -> bool:
        """Return if available."""
        return True

    @property
    def native_value(self) -> StateType:
        """Return native value for entity."""
        value = self.coordinator.data.get("monthly_total").get(self.key).get("cost")
        if value == "":
            value = None
        return value
