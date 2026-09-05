"""Repairs for the KUB integration."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir

from .const import DOMAIN

AUTHENTICATION_ISSUE_ID = "authentication_error"


def async_create_authentication_issue(
    hass: HomeAssistant, entry: ConfigEntry
) -> None:
    """Create a repair issue that directs the user to reauthenticate."""
    ir.async_create_issue(
        hass,
        DOMAIN,
        f"{AUTHENTICATION_ISSUE_ID}_{entry.entry_id}",
        is_fixable=False,
        severity=ir.IssueSeverity.ERROR,
        translation_key=AUTHENTICATION_ISSUE_ID,
    )


def async_delete_authentication_issue(
    hass: HomeAssistant, entry: ConfigEntry
) -> None:
    """Remove the authentication repair issue after a successful request."""
    ir.async_delete_issue(
        hass,
        DOMAIN,
        f"{AUTHENTICATION_ISSUE_ID}_{entry.entry_id}",
    )
