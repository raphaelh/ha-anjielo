"""Shared state: SSE connection to the bridge, retained state, per-topic listeners."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Any

from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback

from .api import AnjieloApi, AnjieloAuthError, AnjieloError

_LOGGER = logging.getLogger(__name__)

Listener = Callable[[str, str], None]  # (relative topic, payload)


class AnjieloBridge:
    """Holds the /api/events stream and dispatches messages to entities."""

    def __init__(
        self,
        hass: HomeAssistant,
        api: AnjieloApi,
        info: dict[str, Any],
        discovery: list[dict[str, Any]],
        state: dict[str, str],
        rtsp_port: int,
    ) -> None:
        self.hass = hass
        self.api = api
        self.info = info
        self.discovery = discovery
        self.state = dict(state)
        self.rtsp_port = rtsp_port
        self.device_id: str = info["device_id"]
        self.connected = False
        self._listeners: dict[str, set[Listener]] = {}
        self._avail_listeners: set[Callable[[], None]] = set()

    # --- topics ------------------------------------------------------------
    @staticmethod
    def rel(topic: str | None) -> str | None:
        """Discovery topic (already relative to the API), or None."""
        return topic or None

    @staticmethod
    def cmd_rel(topic: str) -> str:
        """command_topic "cmd/<key>" -> path under /api/cmd/."""
        return topic.removeprefix("cmd/")

    @property
    def available(self) -> bool:
        return (
            self.connected
            and self.state.get("bridge", "online") == "online"
            and self.state.get("availability", "online") == "online"
        )

    # --- listeners ---------------------------------------------------------
    @callback
    def subscribe(self, topic: str, cb: Listener) -> CALLBACK_TYPE:
        self._listeners.setdefault(topic, set()).add(cb)

        @callback
        def _remove() -> None:
            self._listeners.get(topic, set()).discard(cb)

        return _remove

    @callback
    def subscribe_availability(self, cb: Callable[[], None]) -> CALLBACK_TYPE:
        self._avail_listeners.add(cb)
        return lambda: self._avail_listeners.discard(cb)

    @callback
    def _dispatch(self, topic: str, payload: str) -> None:
        for cb in list(self._listeners.get(topic, ())):
            try:
                cb(topic, payload)
            except Exception:  # a faulty entity must not break the stream
                _LOGGER.exception("Anjielo: error while handling %s", topic)
        if topic in ("bridge", "availability"):
            self._notify_availability()

    @callback
    def _notify_availability(self) -> None:
        for cb in list(self._avail_listeners):
            cb()

    @callback
    def _set_connected(self, value: bool) -> None:
        if self.connected != value:
            self.connected = value
            self._notify_availability()

    # --- SSE loop ----------------------------------------------------------
    async def run(self) -> None:
        """Endless loop (cancelled when the config entry is unloaded)."""
        backoff = 2.0
        while True:
            try:
                async for event, data in self.api.events():
                    if event == "hello":
                        # subscribed before taking the state snapshot: no message lost
                        state = await self.api.state()
                        self.state.update(state)
                        self._set_connected(True)
                        backoff = 2.0
                        _LOGGER.info("Anjielo: connected to bridge %s", self.api.base)
                        for topic, payload in state.items():
                            self._dispatch(topic, payload)
                    elif event == "msg" and isinstance(data, dict):
                        topic = data.get("topic", "")
                        payload = data.get("payload", "")
                        if data.get("retain"):
                            self.state[topic] = payload
                        self._dispatch(topic, payload)
            except asyncio.CancelledError:
                raise
            except AnjieloAuthError:
                _LOGGER.error("Anjielo: token rejected by bridge %s", self.api.base)
                backoff = 60.0
            except AnjieloError as err:
                if self.connected:
                    _LOGGER.warning("Anjielo: bridge lost (%s), reconnecting", err)
                else:
                    _LOGGER.debug("Anjielo: bridge unreachable (%s)", err)
            self._set_connected(False)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60.0)
