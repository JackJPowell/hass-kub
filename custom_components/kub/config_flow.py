"""Config flow for the KUB integration."""

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry, ConfigFlow
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import (
    ConfigEntryAuthFailed,
    ConfigEntryNotReady,
    HomeAssistantError,
)

from .const import CONF_WATER_STATISTICS, DOMAIN
from .kub import kub_utilities

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {vol.Required("username"): str, vol.Required("password"): str}
)


async def validate_input(data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect.

    Data has the keys from STEP_USER_DATA_SCHEMA with values provided by the user.
    """
    try:
        username = data.get("username")
        password = data.get("password")
        kub = kub_utilities.KubUtility(username, password)
        await kub.verify_access()
    except kub_utilities.KUBAuthenticationError as error:
        raise ConfigEntryAuthFailed(error) from error
    except Exception as ex:
        raise ConfigEntryNotReady(ex) from ex

    # Return info that you want to store in the config entry.
    return {
        "title": "KUB",
        "username": username,
        "password": password,
        "data": data,
    }


class KUBConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for KUB."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_CLOUD_POLL

    def __init__(self) -> None:
        """KUB Config Flow."""
        self.api: kub_utilities.KubUtility = None

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry):
        """Get the options flow for this handler."""
        return KUBOptionsFlowHandler(config_entry)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is None or user_input == {}:
            return self.async_show_form(
                step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
            )

        try:
            info = await validate_input(user_input)
        except CannotConnect:
            errors["base"] = "cannot_connect"
        except InvalidAuth:
            errors["base"] = "invalid_auth"
        except Exception:  # pylint: disable=broad-except
            _LOGGER.exception("Unexpected exception")
            errors["base"] = "unknown"
        else:
            return self.async_create_entry(title=info["title"], data=info)

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )

    async def _async_set_unique_id_and_abort_if_already_configured(
        self, unique_id: str
    ) -> None:
        """Set the unique ID and abort if already configured."""
        await self.async_set_unique_id(unique_id)
        self._abort_if_unique_id_configured(
            updates={},
        )


class KUBOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle Unfolded Circle Remote options."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry
        self.options = dict(config_entry.options)

    async def async_step_init(self, user_input=None):  # pylint: disable=unused-argument
        """Manage the options."""
        return await self.async_step_options()

    async def async_step_options(self, user_input=None):
        """Handle options step two flow initialized by the user."""
        if user_input is not None:
            self.options.update(user_input)
            return await self._update_options()

        return self.async_show_form(
            step_id="options",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_WATER_STATISTICS,
                        default=self.config_entry.options.get(
                            CONF_WATER_STATISTICS, False
                        ),
                    ): bool,
                }
            ),
            last_step=True,
        )

    async def _update_options(self):
        """Update config entry options."""
        return self.async_create_entry(title="", data=self.options)


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""
