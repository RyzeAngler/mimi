"""Serialized writes for one ESP32 WebSocket connection."""

from __future__ import annotations

import asyncio
from typing import Any

# The ESP32 WebSocketsClient used by the firmware has a much smaller receive
# limit than the desktop Agent. Keep each binary message comfortably below
# that limit.  PCM is mono s16le, so this size also preserves sample
# alignment.
MAX_DEVICE_AUDIO_FRAME_BYTES = 4096
PCM_SAMPLE_BYTES = 2


class DeviceSession:
    def __init__(self, websocket: Any, device_id: str = "unknown") -> None:
        self.websocket = websocket
        self.device_id = device_id
        self.send_lock = asyncio.Lock()

    async def send_text(self, message: str) -> None:
        async with self.send_lock:
            await self.websocket.send(message)

    async def send_json(self, message: str) -> None:
        await self.send_text(message)

    async def send_audio(self, chunk: bytes) -> None:
        """Send PCM as small binary messages without interleaving writes.

        A TTS provider may yield a large PCM chunk. Sending that provider
        chunk directly can make the ESP32 close the persistent WebSocket with
        RFC 1009 (message too big), even though the Agent's server accepts it.
        Split only at 16-bit sample boundaries and keep the lock for the full
        sequence so speech-control JSON cannot appear between audio frames.
        """

        if not chunk:
            return
        if len(chunk) % PCM_SAMPLE_BYTES:
            raise ValueError("PCM audio must be aligned to 16-bit samples")

        async with self.send_lock:
            for offset in range(0, len(chunk), MAX_DEVICE_AUDIO_FRAME_BYTES):
                await self.websocket.send(
                    chunk[offset : offset + MAX_DEVICE_AUDIO_FRAME_BYTES]
                )
