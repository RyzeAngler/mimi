"""Serialized writes for one ESP32 WebSocket connection."""

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
        self._capabilities: set[str] = set()
        self._speech_ready: dict[str, asyncio.Future[None]] = {}
        self._speech_playback_end: dict[str, asyncio.Future[None]] = {}

    def configure_capabilities(self, capabilities: object) -> None:
        if not isinstance(capabilities, list):
            self._capabilities = set()
            return
        self._capabilities = {
            value for value in capabilities if isinstance(value, str)
        }

    def prepare_speech_flow(self, speech_id: str) -> bool:
        required = {"speech_ready", "speech_playback_end"}
        if not required.issubset(self._capabilities):
            return False
        loop = asyncio.get_running_loop()
        self._speech_ready[speech_id] = loop.create_future()
        self._speech_playback_end[speech_id] = loop.create_future()
        return True

    async def wait_speech_ready(self, speech_id: str, timeout: float) -> None:
        await self._wait_for_signal(self._speech_ready, speech_id, timeout)

    async def wait_speech_playback_end(
        self,
        speech_id: str,
        timeout: float,
    ) -> None:
        await self._wait_for_signal(
            self._speech_playback_end,
            speech_id,
            timeout,
        )

    def mark_speech_ready(self, speech_id: str) -> bool:
        return self._mark_signal(self._speech_ready, speech_id)

    def mark_speech_playback_end(self, speech_id: str) -> bool:
        return self._mark_signal(self._speech_playback_end, speech_id)

    def finish_speech_flow(self, speech_id: str) -> None:
        for waiters in (self._speech_ready, self._speech_playback_end):
            waiter = waiters.pop(speech_id, None)
            if waiter is not None and not waiter.done():
                waiter.cancel()

    def close(self) -> None:
        speech_ids = set(self._speech_ready) | set(self._speech_playback_end)
        for speech_id in speech_ids:
            self.finish_speech_flow(speech_id)

    async def _wait_for_signal(
        self,
        waiters: dict[str, asyncio.Future[None]],
        speech_id: str,
        timeout: float,
    ) -> None:
        waiter = waiters.get(speech_id)
        if waiter is None:
            raise RuntimeError(f"语音会话未注册：{speech_id}")
        await asyncio.wait_for(asyncio.shield(waiter), timeout=timeout)

    def _mark_signal(
        self,
        waiters: dict[str, asyncio.Future[None]],
        speech_id: str,
    ) -> bool:
        waiter = waiters.get(speech_id)
        if waiter is None or waiter.done():
            return False
        waiter.set_result(None)
        return True

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
