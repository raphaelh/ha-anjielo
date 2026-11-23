"""Selects: the intercom's settings (motion sensitivity, alarm interval) and
the video quality of the talk card (HD, or SD for slow links), a setting of
this integration only, kept across restarts."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from . import AnjieloConfigEntry
from .bridge import AnjieloBridge
from .const import signal_uplink
from .entity import AnjieloEntity, device_info, entities_for

# Talk card video: the intercom's HD (~2 Mbit/s in daylight) or SD, the bridge's
# re-encoding (640×360, ~0.2 Mbit/s) for links that cannot carry HD.
VIDEO_QUALITIES = ["hd", "sd"]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AnjieloConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    bridge = entry.runtime_data
    async_add_entities(
        [*(AnjieloSelect(bridge, d) for d in entities_for(bridge, "select")), AnjieloVideoQuality(bridge)]
    )


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


class AnjieloVideoQuality(SelectEntity, RestoreEntity):
    """Video quality of the talk card. Read by the card, not by the bridge."""

    _attr_has_entity_name = True
    _attr_translation_key = "video_quality"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_options = VIDEO_QUALITIES
    _attr_should_poll = False
    _attr_icon = "mdi:video-high-definition"

    def __init__(self, bridge: AnjieloBridge) -> None:
        self.bridge = bridge
        self._attr_unique_id = f"anjielo_{bridge.device_id}_video_quality"
        self._attr_device_info = device_info(bridge)
        self._attr_current_option = "hd"

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if (last := await self.async_get_last_state()) and last.state in VIDEO_QUALITIES:
            self._attr_current_option = last.state
        self.async_on_remove(
            async_dispatcher_connect(self.hass, signal_uplink(self.bridge.device_id), self._on_uplink)
        )

    @callback
    def _on_uplink(self, _mbit: float, quality: str) -> None:
        """The upload test chose a quality."""
        self._attr_current_option = quality
        self.async_write_ha_state()

    async def async_select_option(self, option: str) -> None:
        self._attr_current_option = option
        self.async_write_ha_state()
