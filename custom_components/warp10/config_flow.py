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


def _url_token_schema(defaults: dict[str, Any]) -> vol.Schema:
    """Build the URL/write-token schema, pre-filled from `defaults`."""
    return vol.Schema(
        {
            vol.Required(CONF_URL, default=defaults.get(CONF_URL, DEFAULT_URL)): str,
            vol.Required(
                CONF_WRITE_TOKEN, default=defaults.get(CONF_WRITE_TOKEN, "")
            ): str,
        }
    )


STEP_USER_SCHEMA = _url_token_schema({})


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

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Let the user change the URL and/or write token of an existing entry.

        Without this step, Home Assistant's generic "Reconfigure" UI action
        (always shown for any config entry) has no handler to call and the
        flow errors out.
        """
        errors: dict[str, str] = {}
        reconfigure_entry = self._get_reconfigure_entry()

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
                _LOGGER.exception("Unexpected exception during Warp10 reconfigure")
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(user_input[CONF_URL])
                # Only collide-check against other entries if the URL actually
                # changed — resubmitting the same URL must not abort against
                # this entry's own, unchanged unique_id.
                if self.unique_id != reconfigure_entry.unique_id:
                    self._abort_if_unique_id_configured()
                return self.async_update_reload_and_abort(
                    reconfigure_entry, data=user_input
                )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=_url_token_schema(reconfigure_entry.data),
            errors=errors,
        )

    @staticmethod
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> Warp10OptionsFlow:
        """Return the options flow for this handler."""
        return Warp10OptionsFlow()


class Warp10OptionsFlow(config_entries.OptionsFlow):
    """Handle options: entity filtering, class prefix, batch interval.

    No __init__/config_entry assignment here: OptionsFlow.config_entry is a
    read-only property on the base class (resolved from self.hass/self.handler,
    populated by the flow manager after construction) — manually assigning to
    it, as this class used to do, raises AttributeError as soon as HA tries to
    construct the flow.
    """

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
