"""Mimi Agent WebSocket server entry point."""

import asyncio
import logging

import websockets

from mimi_agent.agent_core.volcengine_ark import VolcengineArkClient
from mimi_agent.audio.pcm import PcmFormat
from mimi_agent.behavior.event_router import EventRouter
from mimi_agent.behavior.speech_policy import SpeechPolicy
from mimi_agent.config import Settings
from mimi_agent.device.websocket import DeviceWebSocketServer
from mimi_agent.observability.logging import LocalLog
from mimi_agent.tts.volcengine_tts import VolcengineTtsProvider
from mimi_agent.vision.llama_server import LlamaServerVlmClient
from mimi_agent.vision.ollama import OllamaVlmClient
from mimi_agent.webui.server import WebUiServer

from .speech_coordinator import SpeechCoordinator
from .vlm_coordinator import VlmCoordinator


def build_runtime(settings: Settings) -> SpeechCoordinator | VlmCoordinator:
    settings.validate_runtime_mode()
    audio_format = PcmFormat(
        sample_rate=settings.audio_sample_rate,
        channels=settings.audio_channels,
        sample_width=settings.audio_sample_width,
    )
    policy = SpeechPolicy(
        default_cooldown_ms=settings.default_speech_cooldown_ms,
        dizzy_cooldown_ms=settings.dizzy_speech_cooldown_ms,
    )
    provider = VolcengineTtsProvider(settings)
    local_log = LocalLog(settings)
    if settings.runtime_mode == "vlm":
        vlm_client = {
            "ollama": OllamaVlmClient,
            "llama-server": LlamaServerVlmClient,
        }[settings.vlm_provider](settings)
        return VlmCoordinator(
            settings=settings,
            provider=provider,
            vlm=vlm_client,
            local_log=local_log,
            webui=WebUiServer(
                settings.webui_host,
                settings.webui_port,
                capture_timeout_seconds=settings.camera_capture_timeout_seconds,
                camera_jpeg_quality=settings.camera_jpeg_quality,
                camera_max_edge=settings.camera_max_edge,
                camera_frame_rate=settings.camera_frame_rate,
                video_window_seconds=settings.vlm_video_window_seconds,
            ),
            voice=settings.volcengine_voice_type,
            audio_format=audio_format,
        )
    return SpeechCoordinator(
        router=EventRouter(policy),
        provider=provider,
        llm=VolcengineArkClient(settings),
        local_log=local_log,
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
        if isinstance(runtime, VlmCoordinator):
            await runtime.start()
        async with websockets.serve(
            device_server.handler,
            settings.host,
            settings.port,
            max_size=64 * 1024,
            ping_interval=20,
            ping_timeout=20,
        ):
            if settings.runtime_mode == "legacy":
                runtime_description = f"LLM provider=ark model={settings.ark_model}"
            else:
                runtime_description = (
                    f"VLM provider={settings.vlm_provider} "
                    f"base_url={settings.vlm_base_url} model={settings.vlm_model}"
                )
            logging.getLogger(__name__).info(
                f"Mimi Agent 已启动，监听 ws://{settings.host}:{settings.port}，"
                f"{runtime_description}。"
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
    settings.validate_runtime_mode()
    settings.validate_tts()
    if settings.runtime_mode == "legacy":
        settings.validate_llm()
    else:
        settings.validate_vlm()
    try:
        asyncio.run(serve(settings))
    except KeyboardInterrupt:
        logging.getLogger(__name__).info("Mimi Agent 已停止。")


if __name__ == "__main__":
    main()
