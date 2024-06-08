"""Diagnostics support for Knoxville Utility Board Integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics.util import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN, KUB_COORDINATOR
from .coordinator import KUBCoordinator

TO_REDACT = {"username", "password", "usage", "account", "locationDetails", "premise"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator: KUBCoordinator = hass.data[DOMAIN][entry.entry_id][KUB_COORDINATOR]
    return async_redact_data(coordinator.data, TO_REDACT)
