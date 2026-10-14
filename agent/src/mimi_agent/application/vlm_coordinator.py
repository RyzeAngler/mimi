"""Coordinate camera capture, sensor triggers, local VLM inference and TTS."""

import asyncio
import logging
import time
import uuid
from contextlib import suppress
from dataclasses import asdict, dataclass

from mimi_agent.agent_core.vlm_prompt import (
    VLM_EXAMPLE_MESSAGES,
    VLM_SYSTEM_PROMPT,
    build_vlm_prompt,
)
from mimi_agent.audio.pcm import PcmFormat
from mimi_agent.behavior.speech_policy import SpeechPolicy
from mimi_agent.config import Settings
from mimi_agent.device.session import DeviceSession
from mimi_agent.observability.logging import LocalLog
from mimi_agent.protocol.codec import encode_motion_ack, encode_speech_error
from mimi_agent.protocol.messages import PhysicalEvent, SensorTelemetry
from mimi_agent.tts.provider import TtsProvider
from mimi_agent.vision.client import VideoClip, VlmClient
from mimi_agent.webui.server import WebUiServer

from .speech_output import SpeechOutput

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _Trigger:
    source: str
    session: DeviceSession | None
    event: PhysicalEvent | None
    request_id: str


class VlmCoordinator:
    """Run one globally serialized VLM turn and keep the legacy path separate."""

    def __init__(
        self,
        settings: Settings,
        provider: TtsProvider,
        vlm: VlmClient,
        local_log: LocalLog,
        webui: WebUiServer,
        voice: str,
        audio_format: PcmFormat,
    ) -> None:
        self.settings = settings
        self.vlm = vlm
        self.local_log = local_log
        self.webui = webui
        self.speech = SpeechOutput(
            provider,
            voice,
            audio_format,
            settings.first_audio_timeout_seconds,
        )
        self._sessions: dict[int, DeviceSession] = {}
        self._telemetry: dict[int, SensorTelemetry] = {}
        self._lock = asyncio.Lock()
        self._active_task: asyncio.Task[None] | None = None
        self._active_session_key: int | None = None
        self._pending_sensor: _Trigger | None = None
        self._last_vlm_content: str | None = None
        self._event_policy = SpeechPolicy(
            default_cooldown_ms=settings.default_speech_cooldown_ms,
            dizzy_cooldown_ms=settings.dizzy_speech_cooldown_ms,
        )
        self._closed = False
        self.webui.on_manual_analyze = self.manual_analyze

    async def start(self) -> None:
        await self.webui.start()
        await self.webui.publish({"type": "agent_state", "state": "idle"})

    async def on_event(self, session: DeviceSession, event: PhysicalEvent) -> None:
        session_key = id(session)
        self._sessions[session_key] = session
        self.local_log.event(event)
        await self.webui.publish(
            {
                "type": "sensor_update",
                "device_id": session.device_id,
                "event": asdict(event),
                "trigger": "sensor_event",
            }
        )
        if self._event_policy.decide(event) is None:
            await session.send_json(encode_motion_ack(event.event_id, False))
            logger.info(
                f"忽略不可行动作事件 event={event.event} "
                f"behavior={event.behavior} intensity={event.intensity:.2f}"
            )
            return
        accepted = await self._enqueue("sensor_event", session, event)
        await session.send_json(encode_motion_ack(event.event_id, accepted))

    async def on_telemetry(
        self,
        session: DeviceSession,
        telemetry: SensorTelemetry,
    ) -> None:
        session_key = id(session)
        self._sessions[session_key] = session
        self._telemetry[session_key] = telemetry
        self.local_log.sensor(telemetry)
        await self.webui.publish(
            {
                "type": "sensor_update",
                "device_id": session.device_id,
                "telemetry": asdict(telemetry),
                "trigger": "telemetry",
            }
        )

    async def manual_analyze(self) -> None:
        session = self._latest_session()
        accepted = await self._enqueue("manual", session, None)
        if not accepted:
            await self.webui.publish(
                {
                    "type": "inference_error",
                    "message": "当前已有一次推理进行中，请等待完成。",
                }
            )

    async def stop_session(self, session: DeviceSession) -> None:
        session_key = id(session)
        task: asyncio.Task[None] | None = None
        async with self._lock:
            self._sessions.pop(session_key, None)
            self._telemetry.pop(session_key, None)
            if (
                self._pending_sensor is not None
                and self._pending_sensor.session is not None
                and id(self._pending_sensor.session) == session_key
            ):
                self._pending_sensor = None
            if self._active_session_key == session_key:
                task = self._active_task
        if task is not None and not task.done():
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

    async def aclose(self) -> None:
        async with self._lock:
            self._closed = True
            self._pending_sensor = None
            active = self._active_task
            self._active_task = None
        if active is not None and not active.done():
            active.cancel()
        if active is not None:
            with suppress(asyncio.CancelledError):
                await active
        await self.webui.close()
        await self.speech.provider.aclose()
        await self.vlm.aclose()
        self.local_log.close()

    async def _enqueue(
        self,
        source: str,
        session: DeviceSession | None,
        event: PhysicalEvent | None,
    ) -> bool:
        trigger = _Trigger(source, session, event, f"vlm-{uuid.uuid4()}")
        async with self._lock:
            if self._closed:
                return False
            if self._active_task is not None and not self._active_task.done():
                if source == "sensor_event":
                    self._pending_sensor = trigger
                    return True
                return False
            self._active_session_key = id(session) if session is not None else None
            self._active_task = asyncio.create_task(
                self._run(trigger),
                name=f"mimi-vlm-{trigger.request_id}",
            )
            return True

    async def _run(self, trigger: _Trigger) -> None:
        started_at = time.perf_counter()
        image: str | None = None
        video: VideoClip | None = None
        try:
            await self.webui.publish(
                {
                    "type": "agent_state",
                    "state": "waiting_for_frame",
                    "trigger": trigger.source,
                    "request_id": trigger.request_id,
                }
            )
            if self.settings.vlm_provider == "llama-server":
                video = await self.webui.capture_video(
                    trigger.source,
                    self.settings.vlm_video_window_seconds,
                )
            else:
                image = await self.webui.capture_frame(trigger.source)
            if self.settings.vlm_provider == "llama-server" and video is None:
                raise RuntimeError("未获取到摄像头视频，本次未请求模型")
            if image is None and video is None and trigger.source != "sensor_event":
                raise RuntimeError("摄像头不可用，无法执行本次视觉分析")
            prompt = build_vlm_prompt(
                trigger.event,
                (
                    self._telemetry.get(id(trigger.session))
                    if trigger.session is not None
                    else None
                ),
            )
            await self.webui.publish(
                {
                    "type": "inference_started",
                    "trigger": trigger.source,
                    "request_id": trigger.request_id,
                    "image_available": image is not None,
                    "video_available": video is not None,
                }
            )
            logged_messages = [f"system:\n{VLM_SYSTEM_PROMPT}"]
            logged_messages.extend(
                f"{message.role}:\n{message.content}"
                for message in VLM_EXAMPLE_MESSAGES
            )
            logged_messages.append(f"user:\n{prompt}")
            self.local_log.llm_input(
                trigger.request_id,
                "\n\n".join(logged_messages),
            )
            content = await self.vlm.complete(
                VLM_SYSTEM_PROMPT,
                prompt,
                image,
                video,
                VLM_EXAMPLE_MESSAGES,
            )
            content = content.strip()
            self.local_log.llm_output(trigger.request_id, content)
            if self._should_suppress_content(content):
                return
            self._last_vlm_content = content
            latency_ms = round((time.perf_counter() - started_at) * 1000)
            await self._publish_result(trigger, content, latency_ms)
            await self._speak(trigger, content)
        except asyncio.CancelledError:
            await self.webui.publish(
                {
                    "type": "agent_state",
                    "state": "cancelled",
                    "trigger": trigger.source,
                    "request_id": trigger.request_id,
                }
            )
            raise
        except Exception as exc:
            logger.exception(f"VLM 处理失败：{trigger.request_id}")
            await self.webui.publish(
                {
                    "type": "inference_error",
                    "trigger": trigger.source,
                    "request_id": trigger.request_id,
                    "message": str(exc),
                }
            )
        finally:
            await self._finish(trigger)

    def _should_suppress_content(self, content: str) -> bool:
        if not content:
            logger.warning(f"忽略空的 VLM 回复：{content!r}")
            return True
        if "something" in content.lower():
            logger.warning("忽略包含英文占位词的 VLM 回复")
            return True
        if self._last_vlm_content is not None:
            previous = " ".join(self._last_vlm_content.split())
            current = " ".join(content.split())
            if current == previous:
                logger.info("忽略重复的 VLM 回复")
                return True
        return False

    async def _publish_result(
        self,
        trigger: _Trigger,
        content: str,
        latency_ms: int,
    ) -> None:
        await self.webui.publish(
            {
                "type": "inference_result",
                "trigger": trigger.source,
                "request_id": trigger.request_id,
                "latency_ms": latency_ms,
                "content": content,
            }
        )

    async def _speak(self, trigger: _Trigger, content: str) -> None:
        speech_id = f"sp-vlm-{uuid.uuid4()}"
        if trigger.session is None:
            logger.warning(
                f"跳过 TTS：没有已连接的 ESP32，speech_id={speech_id}"
            )
            await self.webui.publish(
                {
                    "type": "tts_state",
                    "state": "skipped_no_device",
                    "speech_id": speech_id,
                }
            )
            return
        started_at = time.perf_counter()
        logger.info(
            f"开始 TTS 播放 speech_id={speech_id} "
            f"device_id={trigger.session.device_id} chars={len(content)}"
        )
        await self.webui.publish(
            {
                "type": "tts_state",
                "state": "starting",
                "speech_id": speech_id,
            }
        )
        try:
            playback_confirmed = await self.speech.speak(
                trigger.session,
                speech_id,
                content,
                event_id=trigger.event.event_id if trigger.event else "",
            )
        except asyncio.CancelledError:
            logger.info(f"TTS 播放已取消 speech_id={speech_id}")
            raise
        except Exception as exc:
            logger.exception(
                f"TTS 播放失败 speech_id={speech_id} "
                f"device_id={trigger.session.device_id}"
            )
            with suppress(Exception):
                await trigger.session.send_json(
                    encode_speech_error(
                        speech_id,
                        str(exc),
                        trigger.event.event_id if trigger.event else "",
                    )
                )
            await self.webui.publish(
                {
                    "type": "tts_state",
                    "state": "error",
                    "speech_id": speech_id,
                    "message": str(exc),
                }
            )
            return
        elapsed_ms = (time.perf_counter() - started_at) * 1000
        self.local_log.speech(
            speech_id,
            content,
            elapsed_ms,
            playback_confirmed=playback_confirmed,
        )
        if playback_confirmed:
            logger.info(
                f"TTS 设备播放完成 speech_id={speech_id} "
                f"device_id={trigger.session.device_id} "
                f"elapsed_ms={elapsed_ms:.0f}"
            )
        else:
            logger.info(
                "TTS 音频发送完成但设备未提供播放回执 "
                f"speech_id={speech_id} "
                f"device_id={trigger.session.device_id} "
                f"elapsed_ms={elapsed_ms:.0f}"
            )
        await self.webui.publish(
            {
                "type": "tts_state",
                "state": (
                    "completed" if playback_confirmed else "sent_unconfirmed"
                ),
                "speech_id": speech_id,
            }
        )

    async def _finish(self, trigger: _Trigger) -> None:
        current = asyncio.current_task()
        pending: _Trigger | None = None
        async with self._lock:
            if self._active_task is not current:
                return
            self._active_task = None
            self._active_session_key = None
            if not self._closed and self._pending_sensor is not None:
                pending = self._pending_sensor
                self._pending_sensor = None
                self._active_session_key = (
                    id(pending.session) if pending.session is not None else None
                )
                self._active_task = asyncio.create_task(
                    self._run(pending),
                    name=f"mimi-vlm-{pending.request_id}",
                )
        if pending is None:
            await self.webui.publish(
                {
                    "type": "agent_state",
                    "state": "idle",
                    "trigger": trigger.source,
                }
            )

    def _latest_session(self) -> DeviceSession | None:
        if not self._sessions:
            return None
        return self._sessions[next(reversed(self._sessions))]
