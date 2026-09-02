"""Coordinate physical events, streaming LLM, TTS and device output."""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import suppress
from dataclasses import dataclass, field

from mimi_agent.agent_core.llm import (
    LlmClient,
    LlmMessage,
    LlmSpeechRequest,
)
from mimi_agent.agent_core.conversation import ConversationHistory
from mimi_agent.agent_core.prompt import SYSTEM_PROMPT, build_event_prompt
from mimi_agent.audio.pcm import PcmFormat
from mimi_agent.behavior.event_router import EventRouter
from mimi_agent.device.session import DeviceSession
from mimi_agent.observability import LocalLog
from mimi_agent.protocol.codec import (
    encode_motion_ack,
    encode_speech_cancel,
    encode_speech_end,
    encode_speech_error,
    encode_speech_start,
)
from mimi_agent.protocol.messages import PhysicalEvent, SensorTelemetry
from mimi_agent.tts.provider import TtsProvider, TtsRequest
from mimi_agent.tts.streaming import validated_stream
from mimi_agent.tts.text_chunker import TextChunker

logger = logging.getLogger(__name__)


@dataclass
class _SpeechTurn:
    speech_id: str
    task: asyncio.Task[None]
    priority: int


@dataclass
class _SpeechText:
    received: list[str] = field(default_factory=list)
    committed: list[str] = field(default_factory=list)
    completed: bool = False

    @property
    def full(self) -> str:
        return "".join(self.received)

    @property
    def spoken_prefix(self) -> str:
        return "".join(self.committed)


@dataclass
class _Timeline:
    event_at: float = field(default_factory=time.perf_counter)
    llm_at: float | None = None
    llm_done_at: float | None = None
    tts_at: float | None = None
    first_audio_at: float | None = None
    completed_at: float | None = None


class SpeechCoordinator:
    """Keep one cancellable speech turn per device connection."""

    def __init__(
        self,
        router: EventRouter,
        provider: TtsProvider,
        llm: LlmClient,
        local_log: LocalLog,
        voice: str,
        audio_format: PcmFormat,
        first_audio_timeout_seconds: float = 8.0,
        chunker: TextChunker | None = None,
        conversation_turns: int = 10,
    ) -> None:
        self.router = router
        self.provider = provider
        self.llm = llm
        self.local_log = local_log
        self.voice = voice
        self.audio_format = audio_format
        self.first_audio_timeout_seconds = first_audio_timeout_seconds
        self.chunker = chunker or TextChunker()
        self.conversation_turns = conversation_turns
        self._active: dict[int, _SpeechTurn] = {}
        self._histories: dict[int, ConversationHistory] = {}

    async def on_event(self, session: DeviceSession, event: PhysicalEvent) -> None:
        decision = self.router.route(event)
        self.local_log.event(event)
        if decision is None:
            await session.send_json(encode_motion_ack(event.event_id, False))
            return

        session_key = id(session)
        active = self._active.get(session_key)
        if active is not None and not active.task.done():
            if decision.priority <= active.priority:
                await session.send_json(encode_motion_ack(event.event_id, False))
                return
            active.task.cancel()
            await session.send_json(encode_speech_cancel(active.speech_id))
            with suppress(asyncio.CancelledError):
                await active.task

        await session.send_json(encode_motion_ack(event.event_id, True))
        speech_id = f"sp-{uuid.uuid4()}"
        task = asyncio.create_task(
            self._speak(session, session_key, speech_id, event),
            name=f"mimi-speech-{speech_id}",
        )
        self._active[session_key] = _SpeechTurn(speech_id, task, decision.priority)

    async def on_telemetry(
        self, session: DeviceSession, telemetry: SensorTelemetry
    ) -> None:
        del session
        self.local_log.sensor(telemetry)

    async def stop_session(self, session: DeviceSession) -> None:
        active = self._active.pop(id(session), None)
        if active is not None and not active.task.done():
            active.task.cancel()
            with suppress(asyncio.CancelledError):
                await active.task
        self._histories.pop(id(session), None)

    async def aclose(self) -> None:
        active_turns = tuple(self._active.values())
        self._active.clear()
        self._histories.clear()
        for active in active_turns:
            if not active.task.done():
                active.task.cancel()
        for active in active_turns:
            with suppress(asyncio.CancelledError):
                await active.task
        await self.provider.aclose()
        await self.llm.aclose()
        self.local_log.close()

    async def _speak(
        self,
        session: DeviceSession,
        session_key: int,
        speech_id: str,
        event: PhysicalEvent,
    ) -> None:
        timeline = _Timeline()
        text_state = _SpeechText()
        history = self._histories.setdefault(
            session_key, ConversationHistory(self.conversation_turns)
        )
        event_request = LlmSpeechRequest.from_event(event, ())
        prompt = build_event_prompt(event_request)
        try:
            messages = history.messages(SYSTEM_PROMPT, prompt)
            llm_request = LlmSpeechRequest.from_event(event, messages)
            tts_request = TtsRequest(
                voice=self.voice,
                audio_format=self.audio_format,
                uid=session.device_id,
                additions={
                    "disable_markdown_filter": True,
                    "disable_emoji_filter": False,
                },
            )
            timeline.tts_at = time.perf_counter()
            source = self.provider.stream_text(
                self._tts_text(
                    self._llm_text(
                        llm_request,
                        text_state,
                        timeline,
                        speech_id,
                        history,
                    ),
                    text_state,
                ),
                tts_request,
            )
            audio = validated_stream(source, self.audio_format).__aiter__()
            try:
                first_chunk = await asyncio.wait_for(
                    anext(audio), timeout=self.first_audio_timeout_seconds
                )
            except StopAsyncIteration as exc:
                raise RuntimeError("TTS produced no audio") from exc

            timeline.first_audio_at = time.perf_counter()
            if not text_state.spoken_prefix:
                raise RuntimeError("TTS produced audio before text was committed")
            await session.send_json(
                encode_speech_start(
                    speech_id,
                    text_state.spoken_prefix,
                    self.audio_format,
                    event_id=event.event_id,
                    text_complete=text_state.completed,
                )
            )
            await session.send_audio(first_chunk)
            async for chunk in audio:
                await session.send_audio(chunk)

            if not text_state.completed or not text_state.full.strip():
                raise RuntimeError("LLM did not finish a complete text response")
            await session.send_json(encode_speech_end(speech_id))
            timeline.completed_at = time.perf_counter()
            elapsed = (timeline.completed_at - timeline.event_at) * 1000
            self.local_log.speech(speech_id, text_state.full, elapsed)
            logger.info("语音已完成：第%s轮，内容是“%s”。", speech_id, text_state.full)
        except asyncio.CancelledError:
            logger.info("语音已取消：第%s轮。", speech_id)
            raise
        except Exception as exc:
            logger.exception("语音处理失败：第%s轮。", speech_id)
            with suppress(Exception):
                await session.send_json(
                    encode_speech_error(speech_id, str(exc), event.event_id)
                )
        finally:
            active = self._active.get(session_key)
            if active is not None and active.speech_id == speech_id:
                self._active.pop(session_key, None)

    async def _llm_text(
        self,
        request: LlmSpeechRequest,
        state: _SpeechText,
        timeline: _Timeline,
        speech_id: str,
        history: ConversationHistory,
    ) -> AsyncIterator[str]:
        prompt = request.current_prompt
        self.local_log.llm_input(speech_id, _format_messages(request.messages))
        timeline.llm_at = time.perf_counter()
        async for delta in self.llm.stream_reply(request):
            if not delta:
                continue
            state.received.append(delta)
            yield delta
        if not state.full.strip():
            raise RuntimeError("LLM returned empty text")
        timeline.llm_done_at = time.perf_counter()
        state.completed = True
        history.append(prompt, state.full)
        self.local_log.llm_output(speech_id, state.full)

    async def _tts_text(self, deltas: AsyncIterator[str], state: _SpeechText) -> AsyncIterator[str]:
        async for chunk in self.chunker.stream(deltas):
            state.committed.append(chunk)
            yield chunk


def _format_messages(messages: tuple[LlmMessage, ...]) -> str:
    labels = {"system": "系统设定", "user": "用户输入", "assistant": "Mimi 上一轮回复"}
    lines = []
    for message in messages:
        lines.append(
            f"{labels.get(message.role, message.role)}："
            f"{message.content}"
        )
    return "\n".join(lines)
