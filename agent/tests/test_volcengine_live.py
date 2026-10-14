"""Opt-in live verification of the persistent bidirectional TTS path."""

import os

import pytest

from mimi_agent.audio.pcm import PcmFormat
from mimi_agent.config import Settings
from mimi_agent.tts.provider import TtsRequest
from mimi_agent.tts.volcengine_tts import VolcengineTtsProvider


@pytest.mark.integration
async def test_volcengine_current_configuration_returns_pcm() -> None:
    if os.getenv("MIMI_RUN_LIVE_TESTS") != "1":
        pytest.skip("Set MIMI_RUN_LIVE_TESTS=1 to call the live TTS API")
    settings = Settings.from_env()
    if not (
        settings.volcengine_api_key
        and settings.volcengine_resource_id
        and settings.volcengine_voice_type
    ):
        pytest.skip("Configure the current Volcengine TTS settings first")

    async def text():
        yield "Mimi语音测试。"

    provider = VolcengineTtsProvider(settings)
    request = TtsRequest(
        settings.volcengine_voice_type,
        PcmFormat(
            settings.audio_sample_rate,
            settings.audio_channels,
            settings.audio_sample_width,
        ),
    )
    chunks = [chunk async for chunk in provider.stream_text(text(), request)]
    await provider.aclose()
    audio = b"".join(chunks)
    assert audio
    assert len(audio) % request.audio_format.frame_bytes == 0
