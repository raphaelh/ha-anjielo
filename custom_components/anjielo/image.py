"""Event photos (doorbell, motion, alert), taken by the bridge.

The event stream only carries a notice on image/<kind> ({"time", "size"}) once
a new photo is ready; the JPEG is downloaded from /api/image/<kind> the first
time Home Assistant asks for it (dashboard, notification), then cached.

The notice comes a few seconds after the event that caused it (the bridge
opens the stream and grabs a frame): automations that send the photo should
trigger on this entity's state change, not on the event.
"""

from __future__ import annotations

import logging
from datetime import datetime

from homeassistant.components.image import ImageEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from . import AnjieloConfigEntry
from .api import AnjieloError
from .entity import AnjieloEntity, entities_for, parse_json

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AnjieloConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    bridge = entry.runtime_data
    async_add_entities(AnjieloImage(bridge, d) for d in entities_for(bridge, "image"))


class AnjieloImage(AnjieloEntity, ImageEntity):
    available_without_bridge = True  # a past event / photo
    _attr_content_type = "image/jpeg"

    def __init__(self, bridge, desc) -> None:
        AnjieloEntity.__init__(self, bridge, desc)
        ImageEntity.__init__(self, bridge.hass)
        self.state_rel = bridge.rel(self.conf.get("image_topic"))
        self.kind = (self.state_rel or "").removeprefix("image/")
        self._image: bytes | None = None  # cached JPEG of the current notice

    @callback
    def handle_state(self, payload: str) -> None:
        notice = parse_json(payload)
        if not notice:
            return
        when: datetime | None = None
        if isinstance(t := notice.get("time"), str):
            when = dt_util.parse_datetime(t)
        when = when or dt_util.utcnow()
        if when != self._attr_image_last_updated:
            self._attr_image_last_updated = when
            self._image = None  # downloaded on the next async_image()

    async def async_image(self) -> bytes | None:
        if self._image is None and self._attr_image_last_updated is not None:
            try:
                self._image = await self.bridge.api.image(self.kind)
            except AnjieloError as err:
                _LOGGER.debug("Anjielo: %s photo unavailable (%s)", self.kind, err)
        return self._image
