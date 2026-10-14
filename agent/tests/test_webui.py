import asyncio

from aiohttp import ClientSession

from mimi_agent.vision.client import VideoClip
from mimi_agent.webui.server import WebUiServer


def _bound_port(server: WebUiServer) -> int:
    assert server._runner is not None
    site = next(iter(server._runner.sites))
    assert site._server is not None
    socket = site._server.sockets[0]
    return int(socket.getsockname()[1])


async def test_webui_health_and_request_correlated_camera_frame() -> None:
    server = WebUiServer("127.0.0.1", 0, capture_timeout_seconds=1)
    await server.start()
    port = _bound_port(server)
    try:
        async with ClientSession() as client:
            health = await client.get(f"http://127.0.0.1:{port}/health")
            assert health.status == 200
            assert (await health.json())["ok"] is True

            websocket = await client.ws_connect(f"http://127.0.0.1:{port}/ws")
            initial = await websocket.receive_json()
            assert initial["state"] == "starting"

            capture = asyncio.create_task(server.capture_frame("manual"))
            request = await websocket.receive_json()
            assert request["type"] == "capture_request"
            await websocket.send_json(
                {
                    "type": "camera_frame",
                    "request_id": request["request_id"],
                    "image": "data:image/jpeg;base64,ZmFrZQ==",
                }
            )
            assert await capture == "data:image/jpeg;base64,ZmFrZQ=="
            await websocket.close()
    finally:
        await server.close()


async def test_webui_correlates_binary_video_after_metadata() -> None:
    server = WebUiServer("127.0.0.1", 0, capture_timeout_seconds=1)
    await server.start()
    port = _bound_port(server)
    try:
        async with ClientSession() as client:
            websocket = await client.ws_connect(f"http://127.0.0.1:{port}/ws")
            await websocket.receive_json()

            capture = asyncio.create_task(
                server.capture_video("manual", window_seconds=1)
            )
            request = await websocket.receive_json()
            assert request["type"] == "capture_video_request"
            await websocket.send_json(
                {
                    "type": "camera_video_meta",
                    "request_id": request["request_id"],
                    "format": "mp4",
                    "mime_type": "video/mp4",
                }
            )
            await websocket.send_bytes(b"fake video")

            result = await capture
            assert isinstance(result, VideoClip)
            assert result.data == b"fake video"
            assert result.format == "mp4"
            await websocket.close()
    finally:
        await server.close()


async def test_webui_allows_video_buffer_to_be_shorter_than_requested_window() -> None:
    server = WebUiServer("127.0.0.1", 0, capture_timeout_seconds=1)
    await server.start()
    port = _bound_port(server)
    try:
        async with ClientSession() as client:
            websocket = await client.ws_connect(f"http://127.0.0.1:{port}/ws")
            await websocket.receive_json()

            capture = asyncio.create_task(
                server.capture_video("manual", window_seconds=1)
            )
            request = await websocket.receive_json()
            assert request["type"] == "capture_video_request"
            await websocket.send_json(
                {
                    "type": "camera_video_unavailable",
                    "request_id": request["request_id"],
                    "reason": "video_buffer_empty",
                }
            )

            assert await capture is None
            await websocket.close()
    finally:
        await server.close()
