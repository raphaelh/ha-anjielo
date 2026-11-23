"""Sensors: the intercom's (SD card, doors, monitoring zone), and the upload
speed measured by the upload test (uplink.py)."""

from __future__ import annotations

from homeassistant.components.sensor import RestoreSensor, SensorDeviceClass, SensorEntity
from homeassistant.const import EntityCategory, UnitOfDataRate
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import AnjieloConfigEntry
from .bridge import AnjieloBridge
from .const import signal_uplink
from .entity import AnjieloEntity, device_info, entities_for


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AnjieloConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    bridge = entry.runtime_data
    async_add_entities(
        [*(AnjieloSensor(bridge, d) for d in entities_for(bridge, "sensor")), AnjieloUploadSensor(bridge)]
    )


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


class AnjieloUploadSensor(RestoreSensor):
    """Upload speed of the home connection, from the last upload test."""

    _attr_has_entity_name = True
    _attr_translation_key = "upload_speed"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_device_class = SensorDeviceClass.DATA_RATE
    _attr_native_unit_of_measurement = UnitOfDataRate.MEGABITS_PER_SECOND
    _attr_suggested_display_precision = 2
    _attr_should_poll = False

    def __init__(self, bridge: AnjieloBridge) -> None:
        self.bridge = bridge
        self._attr_unique_id = f"anjielo_{bridge.device_id}_upload_speed"
        self._attr_device_info = device_info(bridge)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if (last := await self.async_get_last_sensor_data()) is not None:
            self._attr_native_value = last.native_value
        self.async_on_remove(
            async_dispatcher_connect(self.hass, signal_uplink(self.bridge.device_id), self._on_uplink)
        )

    @callback
    def _on_uplink(self, mbit: float, _quality: str) -> None:
        self._attr_native_value = round(mbit, 2)
        self.async_write_ha_state()
