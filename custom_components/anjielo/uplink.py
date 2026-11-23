"""Upload test: can the home connection carry the intercom's HD video?

Away from home, the talk card's video leaves through the home connection's
upload. The intercom's HD takes about 2.1 Mbit/s in daylight (peaks 2.5);
an ADSL upload (~0.5 Mbit/s) cannot carry it and the call's sound is lost.
The test uploads random bytes to Cloudflare's speed test endpoint (the one
speed.cloudflare.com uses) for a few seconds, from Home Assistant itself,
and sets the video quality: HD at HD_MIN_MBIT or more, SD otherwise.

Only random bytes are sent, and only when the test button is pressed.
"""

from __future__ import annotations

import os
import time

import aiohttp

UPLOAD_URL = "https://speed.cloudflare.com/__up"
# HD ~2.1 Mbit/s average, 2.5 peaks, + sound and headroom.
HD_MIN_MBIT = 3.0
_BLOCK = os.urandom(256 * 1024)
_MAX_BYTES = 16 * 1024 * 1024


class UplinkTestError(Exception):
    """The upload could not be measured."""


def quality_for(mbit: float) -> str:
    return "hd" if mbit >= HD_MIN_MBIT else "sd"


async def measure_upload(session: aiohttp.ClientSession, budget: float = 20.0) -> float:
    """Upload rate in Mbit/s. Uploads 256 KiB, then 4 times more each round,
    until one round takes 3 s (latency then weighs little) or the budget is
    spent; the last round gives the rate."""
    size = len(_BLOCK)
    spent = 0.0
    rate = 0.0
    while True:
        data = _BLOCK * (size // len(_BLOCK))
        start = time.monotonic()
        try:
            async with session.post(
                UPLOAD_URL,
                data=data,
                headers={"Content-Type": "application/octet-stream"},
                timeout=aiohttp.ClientTimeout(total=max(budget - spent, 5) + 10),
            ) as resp:
                if resp.status >= 400:
                    raise UplinkTestError(f"speed test server answered {resp.status}")
                await resp.read()
        except (aiohttp.ClientError, TimeoutError) as err:
            raise UplinkTestError(str(err) or type(err).__name__) from err
        took = max(time.monotonic() - start, 1e-3)
        spent += took
        rate = len(data) * 8 / took / 1e6
        if took >= 3 or spent >= budget or size >= _MAX_BYTES:
            return rate
        size *= 4
