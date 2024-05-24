"""The KUB integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from KUB import KUBAuthenticationError, kubUtility

from .const import DOMAIN, KUB_API, KUB_COORDINATOR
from .coordinator import KUBCoordinator

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
]

_LOGGER: logging.Logger = logging.getLogger(__package__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up KUB from a config entry."""

    try:
        username = entry.data.get("username")
        password = entry.data.get("password")
        kub = kubUtility(username, password)
        await kub.verify_access()
    except KUBAuthenticationError as error:
        raise ConfigEntryAuthFailed(error) from error
    except Exception as ex:
        raise ConfigEntryNotReady(ex) from ex

    try:
        coordinator = KUBCoordinator(hass, kub)
    except Exception as ex:
        raise ConfigEntryNotReady(ex) from ex

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        KUB_COORDINATOR: coordinator,
        KUB_API: kub,
    }
    await coordinator.async_config_entry_first_refresh()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(update_listener))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


async def update_listener(hass: HomeAssistant, entry: ConfigEntry):
    """Update Listener."""
    await hass.config_entries.async_reload(entry.entry_id)
