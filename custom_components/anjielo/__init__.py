"""Home Assistant integration for the Anjielo video intercom (100% local, via the Anjielo bridge).

The bridge holds the device's ONLY local session. This integration reads the
bridge's API (state, events over SSE, commands) and hands the bridge's RTSP
stream to HA for the camera.
"""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_API_TOKEN, CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import AnjieloApi, AnjieloAuthError, AnjieloError
from .bridge import AnjieloBridge
from .const import CONF_RTSP_PORT, DEFAULT_RTSP_PORT, PLATFORMS

type AnjieloConfigEntry = ConfigEntry[AnjieloBridge]


async def async_setup_entry(hass: HomeAssistant, entry: AnjieloConfigEntry) -> bool:
    api = AnjieloApi(
        async_get_clientsession(hass),
        entry.data[CONF_HOST],
        entry.data[CONF_PORT],
        entry.data.get(CONF_API_TOKEN, ""),
    )
    try:
        info = await api.info()
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
    entry.runtime_data = bridge
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_create_background_task(hass, bridge.run(), "anjielo_sse")
    return True


async def async_unload_entry(hass: HomeAssistant, entry: AnjieloConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
