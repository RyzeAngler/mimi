import asyncio
import json

from mimi_agent.agent_core.llm import LlmSpeechRequest
from mimi_agent.audio.pcm import PcmFormat
from mimi_agent.behavior.event_router import EventRouter
from mimi_agent.behavior.speech_policy import SpeechPolicy
from mimi_agent.config import Settings
from mimi_agent.device.session import DeviceSession
from mimi_agent.application.speech_coordinator import SpeechCoordinator
from mimi_agent.observability import LocalLog
from mimi_agent.protocol.messages import PhysicalEvent


class FakeWebSocket:
    def __init__(self) -> None:
        self.sent: list[str | bytes] = []

    async def send(self, value: str | bytes) -> None:
        self.sent.append(value)


class FakeProvider:
    def __init__(self) -> None:
        self.calls = 0
        self.text: list[str] = []

    async def stream_text(self, text_chunks, request):
        del request
        self.calls += 1
        async for text in text_chunks:
            self.text.append(text)
            if len(self.text) == 1:
                yield b"ab"
        yield b"cd"

    async def aclose(self) -> None:
        pass


class FakeLlm:
    def __init__(self) -> None:
        self.requests: list[LlmSpeechRequest] = []

    async def stream_reply(self, request: LlmSpeechRequest):
        self.requests.append(request)
        await asyncio.sleep(0)
        yield "别晃啦，"
        await asyncio.sleep(0)
        yield "我真的要晕了！"

    async def aclose(self) -> None:
        pass


async def test_event_is_forwarded_as_streaming_speech(tmp_path) -> None:
    socket = FakeWebSocket()
    session = DeviceSession(socket, device_id="test-device")
    settings = Settings(log_dir=tmp_path)
    provider = FakeProvider()
    coordinator = SpeechCoordinator(
        router=EventRouter(SpeechPolicy()),
        provider=provider,
        llm=FakeLlm(),
        local_log=LocalLog(settings),
        voice="test-voice",
        audio_format=PcmFormat(),
    )

    await coordinator.on_event(
        session,
        PhysicalEvent(event_id="evt-1", event="shaking", behavior="dizzy"),
    )
    task = coordinator._active[id(session)].task
    await task

    assert json.loads(socket.sent[0]) == {
        "type": "motion_ack",
        "event_id": "evt-1",
        "will_speak": True,
    }
    assert json.loads(socket.sent[1])["type"] == "speech_start"
    assert json.loads(socket.sent[1])["text"] == "别晃啦，"
    assert json.loads(socket.sent[1])["text_complete"] is False
    assert socket.sent[2:4] == [b"ab", b"cd"]
    assert json.loads(socket.sent[4])["type"] == "speech_end"
    assert provider.calls == 1
    assert "".join(provider.text) == "别晃啦，我真的要晕了！"
    assert "[LLM 输入]" in (tmp_path / "interaction.log").read_text()
    assert "[LLM 输出]" in (tmp_path / "interaction.log").read_text()
    await coordinator.aclose()


async def test_llm_request_keeps_context_per_device_session(tmp_path) -> None:
    socket = FakeWebSocket()
    session = DeviceSession(socket, device_id="test-device")
    settings = Settings(log_dir=tmp_path)
    provider = FakeProvider()
    llm = FakeLlm()
    coordinator = SpeechCoordinator(
        router=EventRouter(SpeechPolicy(default_cooldown_ms=0, dizzy_cooldown_ms=0)),
        provider=provider,
        llm=llm,
        local_log=LocalLog(settings),
        voice="test-voice",
        audio_format=PcmFormat(),
    )

    await coordinator.on_event(
        session,
        PhysicalEvent(event_id="evt-1", event="shaking", behavior="dizzy"),
    )
    await coordinator._active[id(session)].task
    await coordinator.on_event(
        session,
        PhysicalEvent(event_id="evt-2", event="touch", behavior="happy"),
    )
    await coordinator._active[id(session)].task

    messages = llm.requests[1].messages
    assert messages[0].role == "system"
    assert messages[-3].role == "user"
    assert '"event":"shaking"' in messages[-3].content
    assert messages[-2].role == "assistant"
    assert messages[-2].content == "别晃啦，我真的要晕了！"
    assert messages[-1].role == "user"
    assert '"event":"touch"' in messages[-1].content
    await coordinator.aclose()
