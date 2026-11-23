"""Client for the Anjielo bridge HTTP API.

Independent of Home Assistant (aiohttp only) so it can be tested on its own.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

import aiohttp


class AnjieloError(Exception):
    """Generic bridge error."""


class AnjieloAuthError(AnjieloError):
    """Token rejected (401)."""


class AnjieloConnectionError(AnjieloError):
    """Bridge unreachable or invalid response."""


class AnjieloVersionError(AnjieloError):
    """The bridge speaks another API version than this integration."""


def check_api_version(info: dict[str, Any], expected: int) -> None:
    """Raise AnjieloVersionError unless /api/info reports the expected version."""
    got = info.get("api_version")
    if got != expected:
        raise AnjieloVersionError(
            f"bridge API version {got if got is not None else 'unknown (pre-v1)'}, "
            f"this integration needs {expected}: install the bridge add-on and the "
            "integration of the same release"
        )


# SSE lines are split by hand (aiohttp's readline caps at 128 kB); upper bound
# against a stream with no line ending.
_MAX_SSE_LINE = 8 * 1024 * 1024


class AnjieloApi:
    """REST + SSE access to the bridge."""

    def __init__(
        self, session: aiohttp.ClientSession, host: str, port: int, token: str
    ) -> None:
        self._session = session
        self.host = host
        self.port = port
        self.token = token
        self.base = f"http://{host}:{port}"

    @property
    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    async def _request(
        self, method: str, path: str, *, data: str | None = None, timeout: float = 10
    ) -> aiohttp.ClientResponse:
        try:
            resp = await self._session.request(
                method,
                self.base + path,
                headers=self._headers,
                data=data,
                timeout=aiohttp.ClientTimeout(total=timeout),
            )
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise AnjieloConnectionError(f"{method} {path}: {err}") from err
        if resp.status == 401:
            resp.release()
            raise AnjieloAuthError("token rejected")
        return resp

    async def _get_json(self, path: str) -> Any:
        resp = await self._request("GET", path)
        async with resp:
            if resp.status != 200:
                raise AnjieloConnectionError(f"GET {path}: HTTP {resp.status}")
            try:
                return await resp.json(content_type=None)
            except (ValueError, aiohttp.ClientError) as err:
                raise AnjieloConnectionError(f"GET {path}: {err}") from err

    async def info(self) -> dict[str, Any]:
        return await self._get_json("/api/info")

    async def discovery(self) -> list[dict[str, Any]]:
        return await self._get_json("/api/discovery") or []

    async def state(self) -> dict[str, str]:
        return await self._get_json("/api/state") or {}

    async def image(self, kind: str) -> bytes | None:
        """Latest photo (doorbell|motion|alert); None if there is none."""
        resp = await self._request("GET", f"/api/image/{kind}")
        async with resp:
            if resp.status == 404:
                return None
            if resp.status != 200:
                raise AnjieloConnectionError(f"image {kind}: HTTP {resp.status}")
            return await resp.read()

    async def command(self, rel: str, payload: str) -> None:
        """Command for an entity key (e.g. "open_gate", "motion_detection")."""
        resp = await self._request("POST", f"/api/cmd/{rel}", data=payload)
        async with resp:
            if resp.status >= 300:
                raise AnjieloError(f"command {rel}: HTTP {resp.status}")

    async def events(self) -> AsyncIterator[tuple[str, Any]]:
        """SSE stream: ("hello", {...}) then ("msg", {topic, payload, retain}).

        The bridge pings every 25 s: 60 s without a byte means a dead connection.
        """
        try:
            resp = await self._session.get(
                self.base + "/api/events",
                headers=self._headers,
                timeout=aiohttp.ClientTimeout(total=None, connect=10, sock_read=60),
            )
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise AnjieloConnectionError(f"SSE: {err}") from err
        async with resp:
            if resp.status == 401:
                raise AnjieloAuthError("token rejected")
            if resp.status != 200:
                raise AnjieloConnectionError(f"SSE: HTTP {resp.status}")
            parser = SSEParser()
            try:
                async for chunk in resp.content.iter_any():
                    for event, data in parser.feed(chunk):
                        try:
                            yield event, json.loads(data)
                        except ValueError:
                            continue
            except (aiohttp.ClientError, asyncio.TimeoutError) as err:
                raise AnjieloConnectionError(f"SSE: {err}") from err
        raise AnjieloConnectionError("SSE: stream closed by the bridge")


class SSEParser:
    """Splits a text/event-stream into (event, data)."""

    def __init__(self) -> None:
        self._buf = b""
        self._event = "message"
        self._data: list[str] = []

    def feed(self, chunk: bytes) -> list[tuple[str, str]]:
        self._buf += chunk
        out: list[tuple[str, str]] = []
        while True:
            idx = self._buf.find(b"\n")
            if idx < 0:
                if len(self._buf) > _MAX_SSE_LINE:
                    raise AnjieloConnectionError("SSE: line too long")
                return out
            line = self._buf[:idx].rstrip(b"\r").decode("utf-8", "replace")
            self._buf = self._buf[idx + 1 :]
            if not line:
                if self._data:
                    out.append((self._event, "\n".join(self._data)))
                self._event, self._data = "message", []
            elif line.startswith(":"):
                continue  # comment (ping)
            else:
                field, _, value = line.partition(":")
                value = value.removeprefix(" ")
                if field == "event":
                    self._event = value
                elif field == "data":
                    self._data.append(value)
