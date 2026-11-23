"""Buttons: open lock / gate (the intercom), and the upload test (a setting of
this integration, see uplink.py)."""

from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import AnjieloConfigEntry
from .bridge import AnjieloBridge
from .const import signal_uplink
from .entity import AnjieloEntity, device_info, entities_for
from .uplink import UplinkTestError, measure_upload, quality_for

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AnjieloConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    bridge = entry.runtime_data
    async_add_entities(
        [*(AnjieloButton(bridge, d) for d in entities_for(bridge, "button")), AnjieloUplinkTestButton(bridge)]
    )


class AnjieloButton(AnjieloEntity, ButtonEntity):
    async def async_press(self) -> None:
        await self.send(str(self.conf.get("payload_press", "PRESS")))


class AnjieloUplinkTestButton(ButtonEntity):
    """Measure the home connection's upload and set the video quality."""

    _attr_has_entity_name = True
    _attr_translation_key = "test_upload"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:speedometer"
    _attr_should_poll = False

    def __init__(self, bridge: AnjieloBridge) -> None:
        self.bridge = bridge
        self._attr_unique_id = f"anjielo_{bridge.device_id}_test_upload"
        self._attr_device_info = device_info(bridge)

    async def async_press(self) -> None:
        try:
            mbit = await measure_upload(async_get_clientsession(self.hass))
        except UplinkTestError as err:
            raise HomeAssistantError(f"Upload test failed: {err}") from err
        quality = quality_for(mbit)
        _LOGGER.info("Anjielo: upload %.2f Mbit/s -> video quality %s", mbit, quality)
        async_dispatcher_send(self.hass, signal_uplink(self.bridge.device_id), mbit, quality)
