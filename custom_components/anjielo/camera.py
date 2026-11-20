"""Camera: the bridge's RTSP stream (H.264 video + A-law audio), opened on demand.

HA reads the RTSP stream through its built-in go2rtc (WebRTC, audio converted by
HA) or through the stream component (HLS). There is no still image: a thumbnail
is only taken from the stream when it is already running (a Generic Camera
without a still image gives none at all), so a thumbnail never opens the
device's media session.
"""

from __future__ import annotations

import logging
from urllib.parse import quote

from homeassistant.components.camera import Camera, CameraEntityFeature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import AnjieloConfigEntry
from .bridge import AnjieloBridge
from .entity import device_info

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AnjieloConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([AnjieloCamera(entry.runtime_data)])


def rtsp_url(bridge: AnjieloBridge, path_key: str = "av") -> str:
    rtsp = bridge.info.get("rtsp") or {}
    path = (rtsp.get("paths") or {}).get(path_key) or "anjielo"
    user = rtsp.get("user") or "anjielo"
    token = bridge.api.token
    cred = f"{quote(user, safe='')}:{quote(token, safe='')}@" if token else ""
    return f"rtsp://{cred}{bridge.api.host}:{bridge.rtsp_port}/{path}"


class AnjieloCamera(Camera):
    _attr_has_entity_name = True
    _attr_name = None  # use the device name
    _attr_supported_features = CameraEntityFeature.STREAM
    _attr_brand = "Anjielo"
    _attr_should_poll = False

    def __init__(self, bridge: AnjieloBridge) -> None:
        super().__init__()
        self.bridge = bridge
        self._attr_unique_id = f"anjielo_{bridge.device_id}_camera"
        self._attr_device_info = device_info(bridge)
        self._attr_model = bridge.info.get("model")

    @property
    def available(self) -> bool:
        return self.bridge.available

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self.bridge.subscribe_availability(self.async_write_ha_state))

    async def stream_source(self) -> str | None:
        return rtsp_url(self.bridge)

    async def async_camera_image(
        self, width: int | None = None, height: int | None = None
    ) -> bytes | None:
        # Thumbnail only while the stream is already running (someone is watching):
        # never open the device's media session for a dashboard thumbnail.
        stream = self.stream
        thread = getattr(stream, "_thread", None) if stream else None
        if not self.available or thread is None or not thread.is_alive():
            return None
        return await stream.async_get_image(width, height)
