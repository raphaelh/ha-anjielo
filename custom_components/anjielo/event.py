"""Events (doorbell, motion, alert, lock opened, gate opened)."""

from __future__ import annotations

from homeassistant.components.event import EventDeviceClass, EventEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import AnjieloConfigEntry
from .entity import AnjieloEntity, entities_for, parse_json


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AnjieloConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    bridge = entry.runtime_data
    async_add_entities(AnjieloEvent(bridge, d) for d in entities_for(bridge, "event"))


class AnjieloEvent(AnjieloEntity, EventEntity):
    available_without_bridge = True  # a past event / photo
    def __init__(self, bridge, desc) -> None:
        super().__init__(bridge, desc)
        self._attr_event_types = list(self.conf.get("event_types", []))
        if dc := self.conf.get("device_class"):
            self._attr_device_class = EventDeviceClass(dc)
        # attributes come with the event (same topic): no separate subscription
        self.attr_rel = None

    @property
    def extra_state_attributes(self):
        return None  # EventEntity manages its own attributes (event_type + data)

    async def async_added_to_hass(self) -> None:
        # No replay of retained state: the bridge does not retain events.
        b = self.bridge
        self.async_on_remove(b.subscribe_availability(self.async_write_ha_state))
        if self.state_rel:
            self.async_on_remove(b.subscribe(self.state_rel, self._on_event))

    @callback
    def _on_event(self, _topic: str, payload: str) -> None:
        data = parse_json(payload)
        et = data.pop("event_type", None)
        if et not in self._attr_event_types:
            return
        self._trigger_event(et, {k: v for k, v in data.items() if v is not None})
        self.async_write_ha_state()
