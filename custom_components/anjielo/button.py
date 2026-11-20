"""Buttons (open lock / gate)."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import AnjieloConfigEntry
from .entity import AnjieloEntity, entities_for


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AnjieloConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    bridge = entry.runtime_data
    async_add_entities(AnjieloButton(bridge, d) for d in entities_for(bridge, "button"))


class AnjieloButton(AnjieloEntity, ButtonEntity):
    async def async_press(self) -> None:
        await self.send(str(self.conf.get("payload_press", "PRESS")))
