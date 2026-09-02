"""Synthesize one configured phrase and save the streamed PCM for inspection."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

from mimi_agent.audio.pcm import PcmFormat
from mimi_agent.config import Settings
from mimi_agent.tts.provider import TtsRequest
from mimi_agent.tts.volcengine_tts import VolcengineTtsProvider


async def one_text(text: str):
    yield text


async def main() -> None:
    settings = Settings.from_env()
    settings.validate_tts()
    request = TtsRequest(
        voice=settings.volcengine_voice_type,
        audio_format=PcmFormat(
            settings.audio_sample_rate,
            settings.audio_channels,
            settings.audio_sample_width,
        ),
    )
    output = Path(os.getenv("MIMI_TTS_OUTPUT", "cache/tts-smoke.pcm"))
    output.parent.mkdir(parents=True, exist_ok=True)
    provider = VolcengineTtsProvider(settings)
    with output.open("wb") as file:
        async for chunk in provider.stream_text(
            one_text(os.getenv("MIMI_TTS_TEXT", "你好，我是 Mimi。")), request
        ):
            file.write(chunk)
            print(f"received {len(chunk)} bytes")
    await provider.aclose()
    print(f"saved {output}")


if __name__ == "__main__":
    asyncio.run(main())
