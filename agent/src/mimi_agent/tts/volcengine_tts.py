"""Persistent Volcengine V3 bidirectional TTS connection."""

import asyncio
import json
import logging
import uuid
from collections.abc import AsyncIterator, Callable
from contextlib import suppress
from typing import Any

import websockets

from mimi_agent.config import Settings

from .provider import TtsProvider, TtsRequest
from .volcengine_protocol import (
    CANCEL_SESSION,
    CONNECTION_FAILED,
    CONNECTION_STARTED,
    FINISH_CONNECTION,
    FINISH_SESSION,
    SESSION_CANCELED,
    SESSION_FAILED,
    SESSION_FINISHED,
    SESSION_STARTED,
    START_CONNECTION,
    START_SESSION,
    TASK_REQUEST,
    TTS_RESPONSE,
    ServerFrame,
    VolcengineProtocolError,
    encode_event,
    parse_server_frame,
    provider_error,
)

logger = logging.getLogger(__name__)


class TtsConnectionClosed(VolcengineProtocolError):
    """The persistent provider connection closed before the session finished."""


class VolcengineTtsProvider(TtsProvider):
    """Serialize sessions over one healthy WebSocket and reconnect when needed."""

    def __init__(
        self,
        settings: Settings,
        connect: Callable[..., Any] | None = None,
    ) -> None:
        self.settings = settings
        self._connect = connect or websockets.connect
        self._session_lock = asyncio.Lock()
        self._websocket: Any | None = None
        self._connection_context: Any | None = None
        self._reader_task: asyncio.Task[None] | None = None
        self._frames: asyncio.Queue[ServerFrame | Exception] = asyncio.Queue()
        self._closed = False

    def _headers(self, connect_id: str) -> dict[str, str]:
        if not self.settings.volcengine_api_key:
            raise VolcengineProtocolError("VOLCENGINE_API_KEY is required for TTS")
        return {
            "X-Api-Key": self.settings.volcengine_api_key,
            "X-Api-Resource-Id": self.settings.volcengine_resource_id,
            "X-Api-Connect-Id": connect_id,
            "X-Control-Require-Usage-Tokens-Return": "*",
        }

    def _request_params(self, request: TtsRequest, text: str) -> dict[str, Any]:
        audio_params: dict[str, Any] = {
            "format": "pcm",
            "sample_rate": request.audio_format.sample_rate,
        }
        if request.speed_ratio != 1.0:
            audio_params["speech_rate"] = _ratio_to_rate(request.speed_ratio)
        if request.volume_ratio != 1.0:
            audio_params["loudness_rate"] = _ratio_to_rate(request.volume_ratio)
        params: dict[str, Any] = {
            "text": text,
            "speaker": request.voice,
            "audio_params": audio_params,
        }
        if self.settings.volcengine_tts_model:
            params["model"] = self.settings.volcengine_tts_model
        if request.additions:
            params["additions"] = json.dumps(
                request.additions, ensure_ascii=False, separators=(",", ":")
            )
        return params

    async def stream_text(
        self,
        text_chunks: AsyncIterator[str],
        request: TtsRequest,
    ) -> AsyncIterator[bytes]:
        self.settings.validate_tts()
        request.validate()
        async with self._session_lock:
            if self._closed:
                raise TtsConnectionClosed("TTS provider is closed")
            await self._ensure_connected()
            session_id = str(uuid.uuid4())
            sender: asyncio.Task[None] | None = None
            next_frame: asyncio.Task[ServerFrame] | None = None
            session_finished = False
            try:
                await self._send_start_session(session_id, request)
                sender = asyncio.create_task(
                    self._send_text(session_id, text_chunks, request)
                )
                while True:
                    next_frame = asyncio.create_task(self._next_frame())
                    wait_set: set[asyncio.Task[Any]] = {next_frame}
                    if sender is not None and not sender.done():
                        wait_set.add(sender)
                    done, _ = await asyncio.wait(
                        wait_set, return_when=asyncio.FIRST_COMPLETED
                    )
                    if sender is not None and sender in done:
                        error = sender.exception()
                        sender = None
                        if error is not None:
                            raise error
                    if next_frame not in done:
                        next_frame.cancel()
                        with suppress(BaseException):
                            await next_frame
                        next_frame = None
                        continue

                    frame = next_frame.result()
                    next_frame = None
                    if frame.event in {SESSION_FAILED, SESSION_CANCELED}:
                        raise provider_error(frame)
                    if frame.event == TTS_RESPONSE and frame.payload:
                        yield frame.payload
                    elif frame.event == SESSION_FINISHED:
                        detail = frame.json_payload()
                        code = int(detail.get("status_code", 20000000) or 20000000)
                        if code != 20000000:
                            raise provider_error(frame)
                        session_finished = True
                        break

                if sender is not None:
                    await sender
            except asyncio.CancelledError:
                await self._cancel_session(session_id)
                await self._drop_connection()
                raise
            except Exception:
                await self._cancel_session(session_id)
                await self._drop_connection()
                raise
            finally:
                if next_frame is not None and not next_frame.done():
                    next_frame.cancel()
                    with suppress(BaseException):
                        await next_frame
                if sender is not None and not sender.done():
                    sender.cancel()
                    with suppress(BaseException):
                        await sender
                if session_finished:
                    logger.info("TTS session finished and connection remains ready")

    async def _ensure_connected(self) -> None:
        if self._websocket is not None and self._reader_task is not None:
            if not self._reader_task.done():
                return
            await self._drop_connection()

        connect_id = str(uuid.uuid4())
        self._frames = asyncio.Queue()
        self._connection_context = self._connect(
            self.settings.volcengine_tts_bidirectional_url,
            additional_headers=self._headers(connect_id),
            open_timeout=min(self.settings.volcengine_tts_timeout_seconds, 10.0),
            close_timeout=5.0,
            ping_interval=15.0,
            ping_timeout=8.0,
            max_size=2 * 1024 * 1024,
            proxy=None,
        )
        self._websocket = await self._connection_context.__aenter__()
        self._reader_task = asyncio.create_task(self._reader_loop(self._websocket))
        try:
            await self._websocket.send(encode_event(START_CONNECTION))
            frame = await self._next_frame()
            if frame.event == CONNECTION_FAILED:
                raise provider_error(frame)
            if frame.event != CONNECTION_STARTED:
                raise VolcengineProtocolError(
                    f"expected ConnectionStarted, received event={frame.event}"
                )
            logger.info("TTS persistent connection established")
        except Exception:
            await self._drop_connection()
            raise

    async def _send_start_session(self, session_id: str, request: TtsRequest) -> None:
        payload = {
            "event": START_SESSION,
            "namespace": "BidirectionalTTS",
            "user": {"uid": request.uid},
            "req_params": self._request_params(request, ""),
        }
        await self._websocket.send(
            encode_event(START_SESSION, payload, session_id=session_id)
        )
        frame = await self._next_frame()
        if frame.event == SESSION_FAILED:
            raise provider_error(frame)
        if frame.event != SESSION_STARTED:
            raise VolcengineProtocolError(
                f"expected SessionStarted, received event={frame.event}"
            )

    async def _send_text(
        self,
        session_id: str,
        text_chunks: AsyncIterator[str],
        request: TtsRequest,
    ) -> None:
        sent = 0
        async for text in text_chunks:
            if not text or not text.strip():
                continue
            payload = {
                "event": TASK_REQUEST,
                "namespace": "BidirectionalTTS",
                "user": {"uid": request.uid},
                "req_params": self._request_params(request, text),
            }
            await self._websocket.send(
                encode_event(TASK_REQUEST, payload, session_id=session_id)
            )
            sent += 1
        if sent == 0:
            raise VolcengineProtocolError("LLM produced no text for TTS")
        await self._websocket.send(encode_event(FINISH_SESSION, session_id=session_id))

    async def _reader_loop(self, websocket: Any) -> None:
        try:
            while True:
                # The WebSocket client's protocol-level ping/pong keeps this
                # reader alive between speech sessions. Session timeouts are
                # enforced by _next_frame while a handshake or session is active.
                raw = await websocket.recv()
                if not isinstance(raw, bytes):
                    raise VolcengineProtocolError("Volcengine TTS returned a text frame")
                frame = parse_server_frame(raw)
                if frame.error_code is not None:
                    raise provider_error(frame)
                await self._frames.put(frame)
        except asyncio.CancelledError:
            raise
        except websockets.ConnectionClosedOK:
            await self._frames.put(TtsConnectionClosed("TTS connection closed normally"))
        except websockets.ConnectionClosed as exc:
            await self._frames.put(TtsConnectionClosed(f"TTS connection closed: {exc}"))
        except Exception as exc:
            await self._frames.put(exc)

    async def _next_frame(self) -> ServerFrame:
        item = await asyncio.wait_for(
            self._frames.get(), timeout=self.settings.volcengine_tts_timeout_seconds
        )
        if isinstance(item, Exception):
            raise item
        if not isinstance(item, ServerFrame):
            raise TtsConnectionClosed("TTS reader stopped")
        return item

    async def _cancel_session(self, session_id: str) -> None:
        if self._websocket is not None:
            with suppress(Exception):
                await self._websocket.send(
                    encode_event(CANCEL_SESSION, session_id=session_id)
                )

    async def _drop_connection(self) -> None:
        websocket = self._websocket
        context = self._connection_context
        reader = self._reader_task
        self._websocket = None
        self._connection_context = None
        self._reader_task = None
        if reader is not None and reader is not asyncio.current_task():
            reader.cancel()
            with suppress(BaseException):
                await reader
        if websocket is not None:
            with suppress(Exception):
                await websocket.close()
        if context is not None:
            with suppress(Exception):
                await context.__aexit__(None, None, None)

    async def aclose(self) -> None:
        self._closed = True
        if self._websocket is not None:
            with suppress(Exception):
                await self._websocket.send(encode_event(FINISH_CONNECTION))
        await self._drop_connection()


def _ratio_to_rate(ratio: float) -> int:
    return round((ratio - 1.0) * 100)
