"""Reuse the existing TTS-to-device audio lifecycle for non-streaming text."""

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import suppress

from mimi_agent.audio.pcm import PcmFormat
from mimi_agent.device.session import DeviceSession
from mimi_agent.protocol.codec import (
    encode_speech_end,
    encode_speech_start,
)
from mimi_agent.tts.provider import TtsProvider, TtsRequest
from mimi_agent.tts.streaming import validated_stream

logger = logging.getLogger(__name__)


class SpeechOutput:
    """Turn one complete reply into the existing device speech protocol."""

    def __init__(
        self,
        provider: TtsProvider,
        voice: str,
        audio_format: PcmFormat,
        first_audio_timeout_seconds: float,
    ) -> None:
        self.provider = provider
        self.voice = voice
        self.audio_format = audio_format
        self.first_audio_timeout_seconds = first_audio_timeout_seconds

    async def speak(
        self,
        session: DeviceSession,
        speech_id: str,
        text: str,
        event_id: str = "",
    ) -> bool:
        if not text.strip():
            raise ValueError("speech text cannot be empty")
        request = TtsRequest(
            voice=self.voice,
            audio_format=self.audio_format,
            uid=session.device_id,
            additions={
                "disable_markdown_filter": True,
                "disable_emoji_filter": False,
            },
        )
        audio, first_chunk = await self._first_audio(text, request)
        flow_controlled = session.prepare_speech_flow(speech_id)
        audio_bytes = 0
        try:
            await session.send_json(
                encode_speech_start(
                    speech_id,
                    text,
                    self.audio_format,
                    event_id=event_id,
                    text_complete=True,
                )
            )
            if flow_controlled:
                await session.wait_speech_ready(
                    speech_id,
                    self.first_audio_timeout_seconds,
                )

            await session.send_audio(first_chunk)
            audio_bytes += len(first_chunk)
            async for chunk in audio:
                await session.send_audio(chunk)
                audio_bytes += len(chunk)
            await session.send_json(encode_speech_end(speech_id))

            if flow_controlled:
                bytes_per_second = (
                    self.audio_format.sample_rate * self.audio_format.frame_bytes
                )
                audio_seconds = audio_bytes / bytes_per_second
                playback_timeout = max(
                    self.first_audio_timeout_seconds,
                    audio_seconds + 3.0,
                )
                await session.wait_speech_playback_end(
                    speech_id,
                    playback_timeout,
                )
            return flow_controlled
        finally:
            await _close_audio(audio)
            session.finish_speech_flow(speech_id)

    async def _first_audio(
        self,
        text: str,
        request: TtsRequest,
    ) -> tuple[AsyncIterator[bytes], bytes]:
        for attempt in range(2):
            audio = validated_stream(
                self.provider.stream_text(_single_text(text), request),
                self.audio_format,
            ).__aiter__()
            try:
                first_chunk = await asyncio.wait_for(
                    anext(audio), timeout=self.first_audio_timeout_seconds
                )
                return audio, first_chunk
            except asyncio.CancelledError:
                await _close_audio(audio)
                raise
            except StopAsyncIteration:
                error: Exception = RuntimeError("TTS produced no audio")
            except Exception as exc:
                error = exc

            await _close_audio(audio)
            if attempt == 0:
                logger.warning(
                    f"TTS 首帧音频获取失败，将重试一次：{error}"
                )
                continue
            raise error

        raise RuntimeError("TTS first audio retry exhausted")


async def _single_text(text: str) -> AsyncIterator[str]:
    yield text


async def _close_audio(audio: AsyncIterator[bytes]) -> None:
    close = getattr(audio, "aclose", None)
    if close is not None:
        with suppress(BaseException):
            await close()
