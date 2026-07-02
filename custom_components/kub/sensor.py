"""Platform for sensor integration."""

import logging

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.const import UnitOfEnergy, UnitOfVolume
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import StateType

from .const import DOMAIN, KUB_COORDINATOR
from .entity import KUBEntity

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
        self._attr_has_entity_name = True

        match service:
            case "electricity":
                self._attr_device_class = SensorDeviceClass.ENERGY
                self._attr_last_reset = None
                self._attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
                self._attr_state_class = "total_increasing"
                self._attr_name = "Electricity Consumption"
            case "gas":
                self._attr_device_class = SensorDeviceClass.GAS
                self._attr_last_reset = None
                self._attr_native_unit_of_measurement = UnitOfVolume.CENTUM_CUBIC_FEET
                self._attr_state_class = "total_increasing"
                self._attr_suggested_display_precision = 0
                self._attr_name = "Gas Consumption"
            case "water":
                self._attr_device_class = SensorDeviceClass.WATER
                self._attr_last_reset = None
                self._attr_native_unit_of_measurement = UnitOfVolume.CUBIC_FEET
                self._attr_state_class = "total_increasing"
                self._attr_suggested_display_precision = 0
                self._attr_name = "Water Consumption"
            case "wastewater":
                self._attr_device_class = SensorDeviceClass.WATER
                self._attr_last_reset = None
                self._attr_native_unit_of_measurement = UnitOfVolume.CUBIC_FEET
                self._attr_state_class = "total_increasing"
                self._attr_suggested_display_precision = 0
                self._attr_name = "Waste Water Consumption"

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
        self._attr_has_entity_name = True

        match service:
            case "electricity":
                self._attr_device_class = SensorDeviceClass.MONETARY
                self._attr_last_reset = None
                self._attr_native_unit_of_measurement = "USD"
                self._attr_state_class = "total"
                self._attr_name = "Electricity Cost"
            case "gas":
                self._attr_device_class = SensorDeviceClass.MONETARY
                self._attr_last_reset = None
                self._attr_native_unit_of_measurement = "USD"
                self._attr_state_class = "total"
                self._attr_suggested_display_precision = 0
                self._attr_name = "Gas Cost"
            case "water":
                self._attr_device_class = SensorDeviceClass.MONETARY
                self._attr_last_reset = None
                self._attr_native_unit_of_measurement = "USD"
                self._attr_state_class = "total"
                self._attr_suggested_display_precision = 0
                self._attr_name = "Water Cost"
            case "wastewater":
                self._attr_device_class = SensorDeviceClass.MONETARY
                self._attr_last_reset = None
                self._attr_native_unit_of_measurement = "USD"
                self._attr_state_class = "total"
                self._attr_suggested_display_precision = 0
                self._attr_name = "Waste Water Cost"

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
