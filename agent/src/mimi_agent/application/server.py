"""Mimi Agent WebSocket server entry point."""

from __future__ import annotations

import asyncio
import logging

import websockets

from mimi_agent.agent_core.volcengine_ark import VolcengineArkClient
from mimi_agent.audio.pcm import PcmFormat
from mimi_agent.behavior.event_router import EventRouter
from mimi_agent.behavior.speech_policy import SpeechPolicy
from mimi_agent.config import Settings
from mimi_agent.device.websocket import DeviceWebSocketServer
from mimi_agent.observability import LocalLog
from mimi_agent.tts.volcengine_tts import VolcengineTtsProvider

from .speech_coordinator import SpeechCoordinator


def build_runtime(settings: Settings) -> SpeechCoordinator:
    audio_format = PcmFormat(
        sample_rate=settings.audio_sample_rate,
        channels=settings.audio_channels,
        sample_width=settings.audio_sample_width,
    )
    policy = SpeechPolicy(
        default_cooldown_ms=settings.default_speech_cooldown_ms,
        dizzy_cooldown_ms=settings.dizzy_speech_cooldown_ms,
    )
    return SpeechCoordinator(
        router=EventRouter(policy),
        provider=VolcengineTtsProvider(settings),
        llm=VolcengineArkClient(settings),
        local_log=LocalLog(settings),
        voice=settings.volcengine_voice_type,
        audio_format=audio_format,
        first_audio_timeout_seconds=settings.first_audio_timeout_seconds,
        conversation_turns=settings.ark_context_turns,
    )


async def serve(settings: Settings) -> None:
    runtime = build_runtime(settings)
    device_server = DeviceWebSocketServer(
        runtime.on_event,
        runtime.on_telemetry,
        runtime.stop_session,
    )
    try:
        async with websockets.serve(
            device_server.handler,
            settings.host,
            settings.port,
            max_size=64 * 1024,
            ping_interval=20,
            ping_timeout=20,
        ):
            logging.getLogger(__name__).info(
                "Mimi Agent 已启动，监听 ws://%s:%d，LLM 模型为 %s。",
                settings.host,
                settings.port,
                settings.ark_model,
            )
            await asyncio.Future()
    finally:
        await runtime.aclose()


def main() -> None:
    settings = Settings.from_env()
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    settings.validate_tts()
    settings.validate_llm()
    try:
        asyncio.run(serve(settings))
    except KeyboardInterrupt:
        logging.getLogger(__name__).info("Mimi Agent 已停止。")


if __name__ == "__main__":
    main()
