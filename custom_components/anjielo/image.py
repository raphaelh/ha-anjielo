"""Event photos (doorbell, motion, alert), taken by the bridge."""

from __future__ import annotations

import base64
import binascii
import logging

from homeassistant.components.image import ImageEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from . import AnjieloConfigEntry
from .api import AnjieloError
from .entity import AnjieloEntity, entities_for

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AnjieloConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    bridge = entry.runtime_data
    async_add_entities(AnjieloImage(bridge, d) for d in entities_for(bridge, "image"))


class AnjieloImage(AnjieloEntity, ImageEntity):
    _attr_content_type = "image/jpeg"

    def __init__(self, bridge, desc) -> None:
        AnjieloEntity.__init__(self, bridge, desc)
        ImageEntity.__init__(self, bridge.hass)
        # image_topic ".../image/ring": base64 photo in the SSE stream; empty in /api/state
        self.state_rel = bridge.rel(self.conf.get("image_topic"))
        self.kind = (self.state_rel or "").removeprefix("image/")
        self._image: bytes | None = None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()  # replays the retained state -> fetch if present

    @callback
    def handle_state(self, payload: str) -> None:
        if not payload:
            # /api/state does not carry photos: fetch it separately
            self.hass.async_create_task(self._fetch(), eager_start=False)
            return
        try:
            self._set(base64.b64decode(payload, validate=True))
        except (binascii.Error, ValueError):
            _LOGGER.debug("Anjielo: unreadable %s photo", self.kind)

    def _set(self, jpeg: bytes | None) -> None:
        if not jpeg or jpeg == self._image:
            return
        self._image = jpeg
        self._attr_image_last_updated = dt_util.utcnow()

    async def _fetch(self) -> None:
        try:
            jpeg = await self.bridge.api.image(self.kind)
        except AnjieloError as err:
            _LOGGER.debug("Anjielo: %s photo unavailable (%s)", self.kind, err)
            return
        if jpeg and jpeg != self._image:
            self._set(jpeg)
            self.async_write_ha_state()

    async def async_image(self) -> bytes | None:
        return self._image
