"""Selects (motion sensitivity, alarm interval)."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
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
    async_add_entities(AnjieloSelect(bridge, d) for d in entities_for(bridge, "select"))


class AnjieloSelect(AnjieloEntity, SelectEntity):
    def __init__(self, bridge, desc) -> None:
        super().__init__(bridge, desc)
        self._attr_options = list(self.conf.get("options", []))
        self._attr_current_option = None

    @callback
    def handle_state(self, payload: str) -> None:
        self._attr_current_option = payload if payload in self._attr_options else None

    async def async_select_option(self, option: str) -> None:
        await self.send(option)  # the new state comes back from the device over SSE
