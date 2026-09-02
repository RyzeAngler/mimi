"""Run one live Ark -> bidirectional TTS turn and save a playable WAV."""

from __future__ import annotations

import asyncio
import os
import wave
from collections.abc import AsyncIterator
from pathlib import Path

from mimi_agent.agent_core.llm import LlmSpeechRequest
from mimi_agent.agent_core.volcengine_ark import VolcengineArkClient
from mimi_agent.audio.pcm import PcmFormat
from mimi_agent.config import Settings
from mimi_agent.tts.provider import TtsRequest
from mimi_agent.tts.text_chunker import TextChunker
from mimi_agent.tts.volcengine_tts import VolcengineTtsProvider


async def one_text(text: str) -> AsyncIterator[str]:
    yield text


async def main() -> None:
    settings = Settings.from_env()
    settings.validate_llm()
    settings.validate_tts()
    audio_format = PcmFormat(
        settings.audio_sample_rate,
        settings.audio_channels,
        settings.audio_sample_width,
    )
    llm = VolcengineArkClient(settings)
    tts = VolcengineTtsProvider(settings)
    event = LlmSpeechRequest(
        event=os.getenv("MIMI_SMOKE_EVENT", "shaking"),
        behavior=os.getenv("MIMI_SMOKE_BEHAVIOR", "dizzy"),
        intensity=float(os.getenv("MIMI_SMOKE_INTENSITY", "0.8")),
        metadata={},
    )
    try:
        request = TtsRequest(
            voice=settings.volcengine_voice_type,
            audio_format=audio_format,
            uid="mimi-pipeline-smoke",
            additions={"disable_markdown_filter": True},
        )
        pcm = bytearray()
        async for chunk in tts.stream_text(
            TextChunker().stream(llm.stream_reply(event)), request
        ):
            pcm.extend(chunk)
            print(f"received {len(chunk)} PCM bytes")
    finally:
        await tts.aclose()
        await llm.aclose()

    output = Path(os.getenv("MIMI_PIPELINE_OUTPUT", "cache/pipeline-smoke.wav"))
    output.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(output), "wb") as wav:
        wav.setnchannels(audio_format.channels)
        wav.setsampwidth(audio_format.sample_width)
        wav.setframerate(audio_format.sample_rate)
        wav.writeframes(pcm)
    print("streamed Ark text directly into the persistent TTS session")
    print(f"saved: {output} ({len(pcm)} PCM bytes)")


if __name__ == "__main__":
    asyncio.run(main())
