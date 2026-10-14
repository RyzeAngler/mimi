"""HTTP and browser WebSocket service for the local Mimi dashboard."""

import asyncio
import json
import logging
import uuid
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from aiohttp import WSMsgType, web
from aiohttp.web_log import AccessLogger

from mimi_agent.vision.client import VideoClip

logger = logging.getLogger(__name__)

MAX_FRAME_DATA_URL_BYTES = 2 * 1024 * 1024
MAX_VIDEO_BYTES = 16 * 1024 * 1024
_JPEG_PREFIX = "data:image/jpeg;base64,"
_STATIC_DIR = Path(__file__).with_name("static")


class _WebUiAccessLogger(AccessLogger):
    """Ignore malformed connection probes rejected before routing."""

    def log(
        self,
        request: web.Request,
        response: web.StreamResponse,
        time: float,
    ) -> None:
        if request.method == "UNKNOWN" and response.status == 400:
            return
        super().log(request, response, time)

ManualAnalyzeHandler = Callable[[], Awaitable[None]]


class WebUiServer:
    """Serve one local dashboard and correlate frame requests with responses."""

    def __init__(
        self,
        host: str,
        port: int,
        on_manual_analyze: ManualAnalyzeHandler | None = None,
        capture_timeout_seconds: float = 2.0,
        camera_jpeg_quality: float = 0.75,
        camera_max_edge: int = 320,
        camera_frame_rate: float = 4.0,
        video_window_seconds: float = 1.0,
    ) -> None:
        self.host = host
        self.port = port
        self.on_manual_analyze = on_manual_analyze
        self.capture_timeout_seconds = capture_timeout_seconds
        self.camera_jpeg_quality = camera_jpeg_quality
        self.camera_max_edge = camera_max_edge
        self.camera_frame_rate = camera_frame_rate
        self.video_window_seconds = video_window_seconds
        self._runner: web.AppRunner | None = None
        self._clients: set[web.WebSocketResponse] = set()
        self._pending: dict[str, asyncio.Future[str | None]] = {}
        self._pending_videos: dict[str, asyncio.Future[VideoClip | None]] = {}
        self._incoming_videos: dict[web.WebSocketResponse, tuple[str, str, str]] = {}
        self._state: dict[str, Any] = {
            "type": "agent_state",
            "state": "starting",
            "camera": "offline",
            "camera_max_edge": camera_max_edge,
            "camera_jpeg_quality": camera_jpeg_quality,
            "camera_frame_rate": camera_frame_rate,
            "video_window_seconds": video_window_seconds,
        }

    @property
    def camera_ready(self) -> bool:
        return self._state.get("camera") == "ready"

    async def start(self) -> None:
        if self._runner is not None:
            return
        app = web.Application(client_max_size=MAX_VIDEO_BYTES)
        app.router.add_get("/", self._index)
        app.router.add_get("/health", self._health)
        app.router.add_get("/ws", self._websocket)
        runner = web.AppRunner(app, access_log_class=_WebUiAccessLogger)
        await runner.setup()
        try:
            site = web.TCPSite(runner, self.host, self.port)
            await site.start()
        except Exception:
            await runner.cleanup()
            raise
        self._runner = runner
        logger.info(f"Mimi WebUI 已启动，访问 http://localhost:{self.port}。")

    async def close(self) -> None:
        for future in self._pending.values():
            if not future.done():
                future.set_result(None)
        self._pending.clear()
        for future in self._pending_videos.values():
            if not future.done():
                future.set_result(None)
        self._pending_videos.clear()
        self._incoming_videos.clear()
        clients = tuple(self._clients)
        self._clients.clear()
        for client in clients:
            await client.close()
        if self._runner is not None:
            await self._runner.cleanup()
            self._runner = None

    async def publish(self, payload: dict[str, Any]) -> None:
        self._state = {**self._state, **payload}
        message = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        stale: list[web.WebSocketResponse] = []
        for client in tuple(self._clients):
            if client.closed:
                stale.append(client)
                continue
            try:
                await client.send_str(message)
            except ConnectionError:
                stale.append(client)
        for client in stale:
            self._clients.discard(client)

    async def capture_frame(self, trigger: str) -> str | None:
        """Ask the connected browser for one JPEG frame, if available."""

        client = next((item for item in self._clients if not item.closed), None)
        if client is None:
            return None
        request_id = f"cap-{uuid.uuid4()}"
        future: asyncio.Future[str | None] = asyncio.get_running_loop().create_future()
        self._pending[request_id] = future
        try:
            await client.send_json(
                {
                    "type": "capture_request",
                    "request_id": request_id,
                    "trigger": trigger,
                }
            )
            return await asyncio.wait_for(future, self.capture_timeout_seconds)
        except (asyncio.TimeoutError, ConnectionError, RuntimeError):
            return None
        finally:
            self._pending.pop(request_id, None)

    async def capture_video(
        self,
        trigger: str,
        window_seconds: float,
    ) -> VideoClip | None:
        """Ask the connected browser for its recent rolling video window."""

        client = next((item for item in self._clients if not item.closed), None)
        if client is None:
            return None
        request_id = f"cap-video-{uuid.uuid4()}"
        future: asyncio.Future[VideoClip | None] = (
            asyncio.get_running_loop().create_future()
        )
        self._pending_videos[request_id] = future
        try:
            await client.send_json(
                {
                    "type": "capture_video_request",
                    "request_id": request_id,
                    "trigger": trigger,
                    "window_seconds": window_seconds,
                }
            )
            return await asyncio.wait_for(future, self.capture_timeout_seconds)
        except (asyncio.TimeoutError, ConnectionError, RuntimeError):
            return None
        finally:
            self._pending_videos.pop(request_id, None)

    async def _index(self, request: web.Request) -> web.Response:
        del request
        return web.FileResponse(_STATIC_DIR / "index.html")

    async def _health(self, request: web.Request) -> web.Response:
        del request
        return web.json_response({"ok": True, "clients": len(self._clients)})

    async def _websocket(self, request: web.Request) -> web.WebSocketResponse:
        websocket = web.WebSocketResponse(
            heartbeat=30,
            max_msg_size=MAX_VIDEO_BYTES,
        )
        await websocket.prepare(request)
        self._clients.add(websocket)
        await websocket.send_json(self._state)
        logger.info("WebUI 浏览器已连接。")
        try:
            async for message in websocket:
                if message.type == WSMsgType.TEXT:
                    await self._handle_message(websocket, message.data)
                elif message.type == WSMsgType.BINARY:
                    self._resolve_video(websocket, message.data)
                elif message.type in {WSMsgType.CLOSE, WSMsgType.CLOSED, WSMsgType.ERROR}:
                    break
        finally:
            self._clients.discard(websocket)
            self._incoming_videos.pop(websocket, None)
            for future in self._pending.values():
                if not future.done():
                    future.set_result(None)
            for future in self._pending_videos.values():
                if not future.done():
                    future.set_result(None)
            logger.info("WebUI 浏览器已断开。")
        return websocket

    async def _handle_message(
        self,
        websocket: web.WebSocketResponse,
        raw: str,
    ) -> None:
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            await websocket.send_json({"type": "error", "message": "invalid JSON"})
            return
        if not isinstance(payload, dict):
            await websocket.send_json({"type": "error", "message": "message must be an object"})
            return

        message_type = payload.get("type")
        if message_type == "camera_frame":
            self._resolve_frame(payload)
        elif message_type == "camera_video_meta":
            self._prepare_video(websocket, payload)
        elif message_type == "camera_video_unavailable":
            self._resolve_video_unavailable(payload)
        elif message_type == "camera_ready":
            await self.publish(
                {
                    "type": "camera_state",
                    "camera": "ready",
                    "width": payload.get("width"),
                    "height": payload.get("height"),
                }
            )
        elif message_type == "camera_error":
            self._fail_pending_captures()
            await self.publish(
                {
                    "type": "camera_state",
                    "camera": "error",
                    "code": str(payload.get("code") or "unknown"),
                    "message": str(payload.get("message") or "camera error"),
                }
            )
        elif message_type == "manual_analyze" and self.on_manual_analyze is not None:
            asyncio.create_task(
                self.on_manual_analyze(),
                name="mimi-webui-manual-analyze",
            )

    def _fail_pending_captures(self) -> None:
        for future in self._pending.values():
            if not future.done():
                future.set_result(None)
        for future in self._pending_videos.values():
            if not future.done():
                future.set_result(None)

    def _prepare_video(
        self,
        websocket: web.WebSocketResponse,
        payload: dict[str, Any],
    ) -> None:
        request_id = payload.get("request_id")
        video_format = payload.get("format", "auto")
        mime_type = payload.get("mime_type", "")
        if (
            not isinstance(request_id, str)
            or not isinstance(video_format, str)
            or not isinstance(mime_type, str)
        ):
            return
        if video_format not in {"mp4", "ogg", "auto"}:
            return
        if request_id not in self._pending_videos:
            return
        self._incoming_videos[websocket] = (request_id, video_format, mime_type)

    def _resolve_video(
        self,
        websocket: web.WebSocketResponse,
        data: bytes,
    ) -> None:
        metadata = self._incoming_videos.pop(websocket, None)
        if metadata is None:
            return
        request_id, video_format, mime_type = metadata
        future = self._pending_videos.get(request_id)
        if future is None or future.done():
            return
        if not data or len(data) > MAX_VIDEO_BYTES:
            future.set_result(None)
            return
        logger.info(
            f"WebUI 收到视频，request_id={request_id} bytes={len(data)} "
            f"format={video_format} mime_type={mime_type or 'unknown'}"
        )
        future.set_result(VideoClip(data=data, format=video_format))

    def _resolve_video_unavailable(self, payload: dict[str, Any]) -> None:
        request_id = payload.get("request_id")
        if not isinstance(request_id, str):
            return
        logger.warning(
            f"浏览器未提供视频，request_id={request_id} "
            f"reason={payload.get('reason', 'unknown')}"
        )
        future = self._pending_videos.get(request_id)
        if future is not None and not future.done():
            future.set_result(None)

    def _resolve_frame(self, payload: dict[str, Any]) -> None:
        request_id = payload.get("request_id")
        image = payload.get("image")
        if not isinstance(request_id, str) or not isinstance(image, str):
            return
        if not image.startswith(_JPEG_PREFIX):
            return
        if len(image) > MAX_FRAME_DATA_URL_BYTES:
            return
        future = self._pending.get(request_id)
        if future is not None and not future.done():
            future.set_result(image)
