"""Diagnostics ("Download diagnostics") for bug reports, without secrets."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_API_TOKEN
from homeassistant.core import HomeAssistant

from . import AnjieloConfigEntry

TO_REDACT = {CONF_API_TOKEN, "device_id", "token"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: AnjieloConfigEntry
) -> dict[str, Any]:
    bridge = entry.runtime_data
    info = bridge.info
    return {
        "entry": async_redact_data(dict(entry.data), TO_REDACT),
        "bridge": {
            "connected": bridge.connected,
            "available": bridge.available,
            "version": info.get("version"),
            "api_version": info.get("api_version"),
            "rtsp": info.get("rtsp"),
        },
        "discovery": [
            {"component": d.get("component"), "key": d.get("key")}
            for d in bridge.discovery
        ],
        # Retained state as last received (photo notices carry only time and size).
        "state": async_redact_data(dict(sorted(bridge.state.items())), TO_REDACT),
    }
