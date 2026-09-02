import asyncio
import json
import struct

from mimi_agent.audio.pcm import PcmFormat
from mimi_agent.config import Settings
from mimi_agent.tts.provider import TtsRequest
from mimi_agent.tts.volcengine_protocol import (
    CONNECTION_STARTED,
    FINISH_CONNECTION,
    FINISH_SESSION,
    SESSION_FINISHED,
    SESSION_STARTED,
    START_CONNECTION,
    START_SESSION,
    TASK_REQUEST,
    TTS_RESPONSE,
)
from mimi_agent.tts.volcengine_tts import VolcengineTtsProvider


def server_frame(event: int, payload: bytes, *, identifier: str, message_type: int = 9) -> bytes:
    encoded_id = identifier.encode()
    return b"".join(
        [
            bytes((0x11, (message_type << 4) | 4, 0x10 if message_type == 9 else 0x00, 0)),
            struct.pack(">I", event),
            struct.pack(">I", len(encoded_id)),
            encoded_id,
            struct.pack(">I", len(payload)),
            payload,
        ]
    )


class FakeWebSocket:
    def __init__(self) -> None:
        self.sent: list[bytes] = []
        self.responses: asyncio.Queue[bytes] = asyncio.Queue()
        self.sessions = 0
        self.responses.put_nowait(server_frame(CONNECTION_STARTED, b"{}", identifier="conn"))

    async def send(self, value: bytes) -> None:
        self.sent.append(value)
        event = struct.unpack_from(">I", value, 4)[0]
        if event == START_SESSION:
            self.sessions += 1
            self.responses.put_nowait(
                server_frame(SESSION_STARTED, b"{}", identifier=f"session-{self.sessions}")
            )
        elif event == FINISH_SESSION:
            identifier = f"session-{self.sessions}"
            self.responses.put_nowait(
                server_frame(TTS_RESPONSE, b"ab", identifier=identifier, message_type=11)
            )
            self.responses.put_nowait(
                server_frame(TTS_RESPONSE, b"cd", identifier=identifier, message_type=11)
            )
            self.responses.put_nowait(
                server_frame(
                    SESSION_FINISHED,
                    b'{"status_code":20000000}',
                    identifier=identifier,
                )
            )

    async def recv(self) -> bytes:
        return await self.responses.get()

    async def close(self) -> None:
        pass


class FakeConnection:
    def __init__(self, websocket: FakeWebSocket) -> None:
        self.websocket = websocket
        self.enter_count = 0

    def __call__(self, url, **kwargs):
        self.url = url
        self.kwargs = kwargs
        return self

    async def __aenter__(self):
        self.enter_count += 1
        return self.websocket

    async def __aexit__(self, exc_type, exc, tb):
        return False


async def text_chunks():
    yield "别晃啦，"
    yield "我真的要晕了！"


async def test_provider_reuses_one_connection_for_two_sessions() -> None:
    websocket = FakeWebSocket()
    connection = FakeConnection(websocket)
    settings = Settings(
        volcengine_api_key="tts-key",
        volcengine_resource_id="seed-tts-2.0",
        volcengine_voice_type="test-voice",
        volcengine_tts_timeout_seconds=1,
    )
    provider = VolcengineTtsProvider(settings, connect=connection)
    request = TtsRequest("test-voice", PcmFormat())

    first = [chunk async for chunk in provider.stream_text(text_chunks(), request)]
    second = [chunk async for chunk in provider.stream_text(text_chunks(), request)]
    assert first == [b"ab", b"cd"]
    assert second == [b"ab", b"cd"]
    assert connection.enter_count == 1
    events = [struct.unpack_from(">I", frame, 4)[0] for frame in websocket.sent]
    assert events.count(START_CONNECTION) == 1
    assert events.count(START_SESSION) == 2
    assert events.count(TASK_REQUEST) == 4
    assert events.count(FINISH_SESSION) == 2
    assert FINISH_CONNECTION not in events
    await provider.aclose()
    assert struct.unpack_from(">I", websocket.sent[-1], 4)[0] == FINISH_CONNECTION
