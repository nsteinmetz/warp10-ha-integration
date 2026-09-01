"""Diagnostic sensors for the Warp10 integration."""
from __future__ import annotations

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import Warp10Client
from .const import DOMAIN


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the Warp10 diagnostic sensors for a config entry."""
    client: Warp10Client = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            Warp10PointsSentSensor(client, entry),
            Warp10LastErrorSensor(client, entry),
        ]
    )


def _device_info(entry: ConfigEntry) -> dict:
    return {
        "identifiers": {(DOMAIN, entry.entry_id)},
        "name": "Warp 10",
        "manufacturer": "SenX",
        "model": "Warp 10 bridge",
        "entry_type": "service",
    }


class Warp10PointsSentSensor(SensorEntity):
    """Total number of points successfully sent to Warp10 this session."""

    _attr_has_entity_name = True
    _attr_name = "Points sent"
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:database-arrow-up"

    def __init__(self, client: Warp10Client, entry: ConfigEntry) -> None:
        """Initialize the sensor."""
        self._client = client
        self._attr_unique_id = f"{entry.entry_id}_points_sent"
        self._attr_device_info = _device_info(entry)

    @property
    def native_value(self) -> int:
        """Return the total number of points sent."""
        return self._client.points_sent_total


class Warp10LastErrorSensor(SensorEntity):
    """Last error encountered while pushing data to Warp10, if any."""

    _attr_has_entity_name = True
    _attr_name = "Last error"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:alert-circle-outline"

    def __init__(self, client: Warp10Client, entry: ConfigEntry) -> None:
        """Initialize the sensor."""
        self._client = client
        self._attr_unique_id = f"{entry.entry_id}_last_error"
        self._attr_device_info = _device_info(entry)

    @property
    def native_value(self) -> str:
        """Return the last transport error, or 'none'."""
        return self._client.last_error or "none"
