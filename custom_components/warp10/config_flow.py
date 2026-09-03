"""Config flow for the Warp10 integration."""
from __future__ import annotations

import logging
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_BATCH_INTERVAL,
    CONF_CLASS_PREFIX,
    CONF_EXCLUDE,
    CONF_INCLUDE,
    CONF_INGEST_BOOLEAN,
    CONF_INGEST_NUMERIC,
    CONF_INGEST_STRING,
    CONF_URL,
    CONF_WRITE_TOKEN,
    DEFAULT_BATCH_INTERVAL,
    DEFAULT_CLASS_PREFIX,
    DEFAULT_INGEST_BOOLEAN,
    DEFAULT_INGEST_NUMERIC,
    DEFAULT_INGEST_STRING,
    DEFAULT_TIMEOUT,
    DEFAULT_URL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_URL, default=DEFAULT_URL): str,
        vol.Required(CONF_WRITE_TOKEN): str,
    }
)


class InvalidAuth(Exception):
    """Raised when the Warp10 instance rejects the write token."""


async def _validate_connection(hass: HomeAssistant, url: str, token: str) -> None:
    """Push a single harmless point to check the URL and token are valid."""
    session = async_get_clientsession(hass)
    test_line = "// homeassistant.warp10_integration.connection_test{} 1\n"
    async with session.post(
        f"{url.rstrip('/')}/api/v0/update",
        headers={"X-Warp10-Token": token},
        data=test_line,
        timeout=DEFAULT_TIMEOUT,
    ) as resp:
        if resp.status != 200:
            raise InvalidAuth


class Warp10ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Warp10."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step: URL + write token."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                await _validate_connection(
                    self.hass, user_input[CONF_URL], user_input[CONF_WRITE_TOKEN]
                )
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except aiohttp.ClientError:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected exception during Warp10 setup")
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(user_input[CONF_URL])
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title="Warp 10", data=user_input)

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_SCHEMA, errors=errors
        )

    @staticmethod
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> Warp10OptionsFlow:
        """Return the options flow for this handler."""
        return Warp10OptionsFlow(config_entry)


class Warp10OptionsFlow(config_entries.OptionsFlow):
    """Handle options: entity filtering, class prefix, batch interval."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize the options flow."""
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            include = [
                e.strip()
                for e in user_input.get(CONF_INCLUDE, "").split(",")
                if e.strip()
            ]
            exclude = [
                e.strip()
                for e in user_input.get(CONF_EXCLUDE, "").split(",")
                if e.strip()
            ]
            return self.async_create_entry(
                title="",
                data={
                    CONF_INCLUDE: include,
                    CONF_EXCLUDE: exclude,
                    CONF_CLASS_PREFIX: user_input.get(
                        CONF_CLASS_PREFIX, DEFAULT_CLASS_PREFIX
                    ),
                    CONF_BATCH_INTERVAL: user_input.get(
                        CONF_BATCH_INTERVAL, DEFAULT_BATCH_INTERVAL
                    ),
                    CONF_INGEST_NUMERIC: user_input.get(
                        CONF_INGEST_NUMERIC, DEFAULT_INGEST_NUMERIC
                    ),
                    CONF_INGEST_BOOLEAN: user_input.get(
                        CONF_INGEST_BOOLEAN, DEFAULT_INGEST_BOOLEAN
                    ),
                    CONF_INGEST_STRING: user_input.get(
                        CONF_INGEST_STRING, DEFAULT_INGEST_STRING
                    ),
                },
            )

        current = self.config_entry.options
        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_INCLUDE, default=",".join(current.get(CONF_INCLUDE, []))
                ): str,
                vol.Optional(
                    CONF_EXCLUDE, default=",".join(current.get(CONF_EXCLUDE, []))
                ): str,
                vol.Optional(
                    CONF_CLASS_PREFIX,
                    default=current.get(CONF_CLASS_PREFIX, DEFAULT_CLASS_PREFIX),
                ): str,
                vol.Optional(
                    CONF_BATCH_INTERVAL,
                    default=current.get(CONF_BATCH_INTERVAL, DEFAULT_BATCH_INTERVAL),
                ): int,
                vol.Optional(
                    CONF_INGEST_NUMERIC,
                    default=current.get(CONF_INGEST_NUMERIC, DEFAULT_INGEST_NUMERIC),
                ): bool,
                vol.Optional(
                    CONF_INGEST_BOOLEAN,
                    default=current.get(CONF_INGEST_BOOLEAN, DEFAULT_INGEST_BOOLEAN),
                ): bool,
                vol.Optional(
                    CONF_INGEST_STRING,
                    default=current.get(CONF_INGEST_STRING, DEFAULT_INGEST_STRING),
                ): bool,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
