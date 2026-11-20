"""Switches (motion detection, detection zone)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
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
    async_add_entities(AnjieloSwitch(bridge, d) for d in entities_for(bridge, "switch"))


class AnjieloSwitch(AnjieloEntity, SwitchEntity):
    def __init__(self, bridge, desc) -> None:
        super().__init__(bridge, desc)
        self._on = str(self.conf.get("payload_on", "true"))
        self._off = str(self.conf.get("payload_off", "false"))
        self._attr_is_on = None

    @callback
    def handle_state(self, payload: str) -> None:
        self._attr_is_on = {self._on: True, self._off: False}.get(payload)

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.send(self._on)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.send(self._off)
