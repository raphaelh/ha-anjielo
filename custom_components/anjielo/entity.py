"""Base entity: one entry of the bridge's /api/discovery."""

from __future__ import annotations

import json
from typing import Any

from homeassistant.const import EntityCategory
from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity

from .bridge import AnjieloBridge
from .const import DOMAIN, TRANSLATED_KEYS


def device_info(bridge: AnjieloBridge) -> DeviceInfo:
    info = bridge.info
    return DeviceInfo(
        identifiers={(DOMAIN, bridge.device_id)},
        name="Intercom",  # fixed English name (the bridge reports its local device name)
        manufacturer=info.get("manufacturer"),
        sw_version=info.get("version"),
        configuration_url=None,
    )


def entities_for(bridge: AnjieloBridge, component: str) -> list[dict[str, Any]]:
    return [d for d in bridge.discovery if d.get("component") == component]


def parse_json(payload: str) -> dict[str, Any]:
    try:
        v = json.loads(payload)
    except (TypeError, ValueError):
        return {}
    return v if isinstance(v, dict) else {}


class AnjieloEntity(Entity):
    """Entity driven by the topics of its discovery config."""

    # Past facts (last ring, last photo) stay true while the bridge is away:
    # such entities keep their value instead of going unavailable. That also
    # keeps them restorable: Home Assistant does not restore an event (or a
    # button) whose last saved state was "unavailable", so a restart during a
    # bridge update used to lose the last ring.
    available_without_bridge = False

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, bridge: AnjieloBridge, desc: dict[str, Any]) -> None:
        self.bridge = bridge
        self.key: str = desc["key"]
        self.conf: dict[str, Any] = desc.get("config", {})
        conf = self.conf
        self._attr_unique_id = f"anjielo_{bridge.device_id}_{self.key}"
        if self.key in TRANSLATED_KEYS:
            self._attr_translation_key = self.key  # English name from translations
        else:
            self._attr_name = conf.get("name")
        self._attr_device_info = device_info(bridge)
        if icon := conf.get("icon"):
            self._attr_icon = icon
        if cat := conf.get("entity_category"):
            self._attr_entity_category = EntityCategory(cat)
        self.state_rel = bridge.rel(conf.get("state_topic"))
        self.attr_rel = bridge.rel(conf.get("json_attributes_topic"))
        self._attrs: dict[str, Any] = {}

    @property
    def available(self) -> bool:
        return self.available_without_bridge or self.bridge.available

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        return self._attrs or None

    async def async_added_to_hass(self) -> None:
        b = self.bridge
        self.async_on_remove(b.subscribe_availability(self.async_write_ha_state))
        if self.state_rel:
            self.async_on_remove(b.subscribe(self.state_rel, self._on_state))
            if self.state_rel in b.state:
                self.handle_state(b.state[self.state_rel])
        if self.attr_rel and self.attr_rel != self.state_rel:
            self.async_on_remove(b.subscribe(self.attr_rel, self._on_attrs))
            if self.attr_rel in b.state:
                self._attrs = parse_json(b.state[self.attr_rel])

    @callback
    def _on_state(self, _topic: str, payload: str) -> None:
        self.handle_state(payload)
        self.async_write_ha_state()

    @callback
    def _on_attrs(self, _topic: str, payload: str) -> None:
        self._attrs = parse_json(payload)
        self.async_write_ha_state()

    @callback
    def handle_state(self, payload: str) -> None:
        """Override: apply a state_topic payload."""

    async def send(self, payload: str) -> None:
        await self.bridge.api.command(self.bridge.cmd_rel(self.conf["command_topic"]), payload)
