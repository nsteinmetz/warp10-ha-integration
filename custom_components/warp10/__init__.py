"""The Warp10 integration for Home Assistant.

Listens to state_changed events, buffers numeric states, and flushes them
periodically to a Warp10 instance via the /api/v0/update HTTP endpoint,
using each state's own last_updated timestamp (raw stream, no aggregation).
"""
from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from urllib.parse import quote as urlquote

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_DEVICE_CLASS, EVENT_STATE_CHANGED, Platform
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_time_interval

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
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]

_IGNORED_STATES = ("unknown", "unavailable", "")

# Warp10's GTS input format has a native BOOLEAN value type, written as an
# unquoted T/F literal (see GTSHelper.BOOLEAN_VALUE_RE in warp10-platform,
# which also accepts "true"/"false"). Home Assistant's on/off domains
# (binary_sensor, switch, input_boolean, ...) report "on"/"off", so both
# spellings are mapped here rather than being dropped as non-numeric.
_BOOLEAN_STATES = {"on": "T", "true": "T", "off": "F", "false": "F"}


class Warp10Client:
    """Buffers state changes and flushes them to Warp10 in batches."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the client from a config entry."""
        self.hass = hass
        self.entry = entry
        self.session = async_get_clientsession(hass)
        self.update_url = entry.data[CONF_URL].rstrip("/") + "/api/v0/update"
        self.token = entry.data[CONF_WRITE_TOKEN]

        self.class_prefix = entry.options.get(CONF_CLASS_PREFIX, DEFAULT_CLASS_PREFIX)
        self.include = set(entry.options.get(CONF_INCLUDE, []))
        self.exclude = set(entry.options.get(CONF_EXCLUDE, []))
        self.ingest_numeric = entry.options.get(
            CONF_INGEST_NUMERIC, DEFAULT_INGEST_NUMERIC
        )
        self.ingest_boolean = entry.options.get(
            CONF_INGEST_BOOLEAN, DEFAULT_INGEST_BOOLEAN
        )
        self.ingest_string = entry.options.get(
            CONF_INGEST_STRING, DEFAULT_INGEST_STRING
        )

        self._buffer: list[str] = []
        self._lock = asyncio.Lock()

        # Simple diagnostics, surfaced via sensor.py
        self.last_error: str | None = None
        self.points_sent_total = 0

    def _entity_allowed(self, entity_id: str) -> bool:
        """Return True if the entity should be forwarded to Warp10."""
        if self.include and entity_id not in self.include:
            return False
        if entity_id in self.exclude:
            return False
        return True

    def _area_id_for_entity(self, entity_id: str) -> str | None:
        """Return the entity's area_id, direct or inherited from its device.

        area_id (a stable slug) is used rather than the area's display name:
        renaming an area in the UI would otherwise change the label value and
        fragment the GTS's identity in Warp10 across the rename.
        """
        entity_entry = er.async_get(self.hass).async_get(entity_id)
        if entity_entry is None:
            return None
        if entity_entry.area_id:
            return entity_entry.area_id
        if entity_entry.device_id:
            device_entry = dr.async_get(self.hass).async_get(entity_entry.device_id)
            if device_entry:
                return device_entry.area_id
        return None

    @staticmethod
    def _escape_label_value(value: str) -> str:
        """Escape a label value per the Warp10 GTS input format.

        Reserved characters (backslash, comma, equals sign, single quote)
        must be backslash-escaped inside class names and label values.
        """
        return (
            value.replace("\\", "\\\\")
            .replace(",", "\\,")
            .replace("=", "\\=")
            .replace("'", "\\'")
        )

    @callback
    def handle_state_change(self, event: Event) -> None:
        """Queue a state change for the next flush (called synchronously)."""
        new_state = event.data.get("new_state")
        if new_state is None:
            return

        entity_id = new_state.entity_id
        if not self._entity_allowed(entity_id):
            return

        if new_state.state in _IGNORED_STATES:
            return

        boolean_value = _BOOLEAN_STATES.get(new_state.state.lower())
        if boolean_value is not None:
            if not self.ingest_boolean:
                return
            value: str | int | float = boolean_value
        else:
            try:
                value = float(new_state.state)
            except ValueError:
                if not self.ingest_string:
                    return
                # Free-text state: forward as a Warp10 STRING value. Values are
                # whitespace-delimited in the GTS input format and percent-decoded
                # on ingestion (see GTSHelper.parseValue), so the content must be
                # percent-encoded before being quoted.
                value = f"'{urlquote(new_state.state, safe='')}'"
            else:
                if not self.ingest_numeric:
                    return
                if value.is_integer():
                    value = int(value)

        ts_micros = int(new_state.last_updated.timestamp() * 1_000_000)
        class_name = f"{self.class_prefix}.{entity_id}"

        labels: dict[str, str] = {}
        area_id = self._area_id_for_entity(entity_id)
        if area_id:
            labels["area_id"] = area_id
        device_class = new_state.attributes.get(ATTR_DEVICE_CLASS)
        if device_class:
            labels["device_class"] = str(device_class)
        label_str = ",".join(
            f"{k}={self._escape_label_value(v)}" for k, v in labels.items()
        )

        line = f"{ts_micros}// {class_name}{{{label_str}}} {value}"
        self._buffer.append(line)

    async def async_flush(self, _now=None) -> None:
        """Send buffered points to Warp10 as a single batched request."""
        async with self._lock:
            if not self._buffer:
                return
            payload = "\n".join(self._buffer) + "\n"
            count = len(self._buffer)
            self._buffer = []

        try:
            async with self.session.post(
                self.update_url,
                headers={"X-Warp10-Token": self.token},
                data=payload,
                timeout=DEFAULT_TIMEOUT,
            ) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    self.last_error = f"HTTP {resp.status}: {body[:200]}"
                    _LOGGER.warning(
                        "Warp10 rejected %d point(s): %s", count, self.last_error
                    )
                else:
                    self.last_error = None
                    self.points_sent_total += count
                    _LOGGER.debug("Sent %d point(s) to Warp10", count)
        except Exception as err:  # noqa: BLE001 - report any transport error, keep running
            self.last_error = str(err)
            _LOGGER.warning("Failed to send %d point(s) to Warp10: %s", count, err)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Warp10 from a config entry."""
    client = Warp10Client(hass, entry)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = client

    interval = entry.options.get(CONF_BATCH_INTERVAL, DEFAULT_BATCH_INTERVAL)

    unsub_listener = hass.bus.async_listen(
        EVENT_STATE_CHANGED, client.handle_state_change
    )
    unsub_timer = async_track_time_interval(
        hass, client.async_flush, timedelta(seconds=interval)
    )

    entry.async_on_unload(unsub_listener)
    entry.async_on_unload(unsub_timer)
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry, flushing any pending points first."""
    client: Warp10Client = hass.data[DOMAIN][entry.entry_id]
    await client.async_flush()
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the config entry when its options change."""
    await hass.config_entries.async_reload(entry.entry_id)
