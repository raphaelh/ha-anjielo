"""Sensors (SD card, doors, monitoring zone)."""

from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import AnjieloConfigEntry
from .entity import AnjieloEntity, entities_for


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AnjieloConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    bridge = entry.runtime_data
    async_add_entities(AnjieloSensor(bridge, d) for d in entities_for(bridge, "sensor"))


class AnjieloSensor(AnjieloEntity, SensorEntity):
    def __init__(self, bridge, desc) -> None:
        super().__init__(bridge, desc)
        self._enum = self.conf.get("device_class") == "enum"
        if self._enum:
            self._attr_device_class = SensorDeviceClass.ENUM
            self._attr_options = list(self.conf.get("options", []))

    @callback
    def handle_state(self, payload: str) -> None:
        if self._enum and payload not in self._attr_options:
            self._attr_native_value = None
            return
        self._attr_native_value = payload or None
