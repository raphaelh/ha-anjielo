"""Home Assistant integration for the Anjielo video intercom (100% local, via the Anjielo bridge).

The bridge holds the device's ONLY local session. This integration reads the
bridge's API (state, events over SSE, commands) and hands the bridge's RTSP
stream to HA for the camera. It also serves a dashboard card to answer the
intercom (www/anjielo-talk-card.js: video, sound and microphone over HA's own
WebRTC, on the "Talk" camera).
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_API_TOKEN, CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType

from .api import AnjieloApi, AnjieloAuthError, AnjieloError, check_api_version
from .bridge import AnjieloBridge
from .const import API_VERSION, CONF_RTSP_PORT, DEFAULT_RTSP_PORT, DOMAIN, PLATFORMS

type AnjieloConfigEntry = ConfigEntry[AnjieloBridge]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

CARD_URL = "/anjielo/anjielo-talk-card.js"


def _file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Serve the talk card and load it in every dashboard."""
    card = Path(__file__).parent / "www" / "anjielo-talk-card.js"
    await hass.http.async_register_static_paths([StaticPathConfig(CARD_URL, str(card), False)])
    # A hash of the file in the URL makes browsers fetch the card again when it changes.
    digest = await hass.async_add_executor_job(_file_digest, card)
    if "frontend" in hass.config.components:
        add_extra_js_url(hass, f"{CARD_URL}?v={digest}")
    return True


async def async_setup_entry(hass: HomeAssistant, entry: AnjieloConfigEntry) -> bool:
    api = AnjieloApi(
        async_get_clientsession(hass),
        entry.data[CONF_HOST],
        entry.data[CONF_PORT],
        entry.data.get(CONF_API_TOKEN, ""),
    )
    try:
        info = await api.info()
        # Not ready (retried) rather than failed: updating the bridge fixes it.
        check_api_version(info, API_VERSION)
        discovery = await api.discovery()
        state = await api.state()
    except AnjieloAuthError as err:
        raise ConfigEntryAuthFailed(str(err)) from err
    except AnjieloError as err:
        raise ConfigEntryNotReady(str(err)) from err

    bridge = AnjieloBridge(
        hass,
        api,
        info,
        discovery,
        state,
        entry.data.get(CONF_RTSP_PORT, DEFAULT_RTSP_PORT),
    )
    bridge.app_device = _app_device(hass)
    entry.runtime_data = bridge
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_create_background_task(hass, bridge.run(), "anjielo_sse")
    return True


def _app_device(hass: HomeAssistant) -> str | None:
    """The registry id of the Anjielo Bridge add-on's device, created by the
    Supervisor integration (slug "local_anjielo_bridge", or
    "<repository>_anjielo_bridge")."""
    reg = dr.async_get(hass)
    for entry in hass.config_entries.async_entries("hassio"):
        for device in dr.async_entries_for_config_entry(reg, entry.entry_id):
            for domain, ident in device.identifiers:
                if domain == "hassio" and (ident == "anjielo_bridge" or ident.endswith("_anjielo_bridge")):
                    return device.id
    return None


async def async_unload_entry(hass: HomeAssistant, entry: AnjieloConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
