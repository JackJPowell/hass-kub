"""Base entity for KUB Integration"""

from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, KUB_COORDINATOR
from .coordinator import KUBCoordinator


async def async_setup_entry(hass: HomeAssistant, config_entry):
    """Add sensors for passed config_entry in HA."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id][KUB_COORDINATOR]


class KUBEntity(CoordinatorEntity[KUBCoordinator]):
    """Common entity class for all KUB entities"""

    def __init__(self, coordinator) -> None:
        """Initialize KUB Entity."""
        super().__init__(coordinator)
        self.coordinator = coordinator
        self.coordinator.entities.append(self)

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device info."""
        return DeviceInfo(
            identifiers={
                # Serial numbers are unique identifiers within a specific domain
                (DOMAIN, "KUB")
            },
            name="KUB",
            manufacturer="Knoxville Utilities Board",
            configuration_url="https://www.kub.org",
        )

    @property
    def should_poll(self) -> bool:
        return False
