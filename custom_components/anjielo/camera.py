"""Camera: the bridge's video-only RTSP stream (H.264), opened on demand.

Video only on purpose: the bridge's audio stream needs start-talk, which turns
on the intercom's microphone, opens a call limited to about 2 minutes (the
bridge rotates the session every 110 s, with a short gap) and is the most
sensitive command for the device. The intercom sends no audio in a plain live
view, so sound belongs to a call ("answer"), not to the camera preview. The
audio stream stays available at rtsp_url(bridge, "av").

A second camera, "Talk" (disabled by default), streams the bridge's
push-to-talk path for two-way audio (the integration's talk card): video,
sound and an RTSP backchannel. The bridge opens the call (start-talk) only
while voice arrives on the backchannel and closes it after a short silence,
so the card keeps one session open and talks without setting up another.
A third, "Talk (SD)" (disabled by default), is the same with the video
re-encoded in SD by the bridge (640×360, ~200 kbit/s), for slow links. Kept as
entities so the card can name them and the stream credentials stay inside HA.

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
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import AnjieloConfigEntry
from .bridge import AnjieloBridge
from .const import DOMAIN
from .entity import device_info

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AnjieloConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    bridge = entry.runtime_data
    # The SD talk camera was "talk_lite" before 0.1.0 was released: keep the
    # same entity (id, settings) under the new unique id.
    reg = er.async_get(hass)
    old = f"anjielo_{bridge.device_id}_camera_talk_lite"
    new = f"anjielo_{bridge.device_id}_camera_talk_sd"
    if (eid := reg.async_get_entity_id("camera", DOMAIN, old)) and not reg.async_get_entity_id("camera", DOMAIN, new):
        reg.async_update_entity(eid, new_unique_id=new)
    async_add_entities([AnjieloCamera(bridge), AnjieloTalkCamera(bridge), AnjieloTalkSDCamera(bridge)])


RTSP_DEFAULT_PATHS = {
    "av": "anjielo",
    "video": "anjielo_video",
    "talk": "anjielo_talk",
    "talk_sd": "anjielo_talk_sd",
}


def rtsp_url(bridge: AnjieloBridge, path_key: str = "video") -> str:
    rtsp = bridge.info.get("rtsp") or {}
    path = (rtsp.get("paths") or {}).get(path_key) or RTSP_DEFAULT_PATHS[path_key]
    user = rtsp.get("user") or "anjielo"
    token = bridge.api.token
    cred = f"{quote(user, safe='')}:{quote(token, safe='')}@" if token else ""
    return f"rtsp://{cred}{bridge.api.host}:{bridge.rtsp_port}/{path}"


class _AnjieloCameraBase(Camera):
    _attr_has_entity_name = True
    _attr_supported_features = CameraEntityFeature.STREAM
    _attr_brand = "Anjielo"
    _attr_should_poll = False
    _unique_suffix = "camera"
    _path_key = "video"

    def __init__(self, bridge: AnjieloBridge) -> None:
        super().__init__()
        self.bridge = bridge
        self._attr_unique_id = f"anjielo_{bridge.device_id}_{self._unique_suffix}"
        self._attr_device_info = device_info(bridge)

    @property
    def available(self) -> bool:
        return self.bridge.available

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self.bridge.subscribe_availability(self.async_write_ha_state))

    async def stream_source(self) -> str | None:
        return rtsp_url(self.bridge, self._path_key)

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


class AnjieloCamera(_AnjieloCameraBase):
    """Live view: video only, no call."""

    _attr_name = None  # use the device name


class AnjieloTalkCamera(_AnjieloCameraBase):
    """Video, sound and talk (RTSP backchannel): a call, for two-way audio cards."""

    _attr_translation_key = "talk"
    _attr_entity_registry_enabled_default = False
    _unique_suffix = "camera_talk"
    _path_key = "talk"


class AnjieloTalkSDCamera(AnjieloTalkCamera):
    """The talk camera with SD video (re-encoded 640×360 ~200 kbit/s by the
    bridge), for slow links: a phone away from home behind an ADSL upload."""

    _attr_translation_key = "talk_sd"
    _unique_suffix = "camera_talk_sd"
    _path_key = "talk_sd"
