import asyncio
import json

import httpx

from mimi_agent.agent_core.llm import LlmMessage
from mimi_agent.application.vlm_coordinator import VlmCoordinator
from mimi_agent.application.speech_output import SpeechOutput
from mimi_agent.audio.pcm import PcmFormat
from mimi_agent.config import Settings
from mimi_agent.device.session import DeviceSession
from mimi_agent.observability.logging import LocalLog
from mimi_agent.protocol.messages import MotionSummary, PhysicalEvent
from mimi_agent.vision.client import VideoClip
from mimi_agent.vision.llama_server import LlamaServerVlmClient
from mimi_agent.vision.ollama import OllamaVlmClient


class FakeWebSocket:
    def __init__(self) -> None:
        self.sent: list[str | bytes] = []

    async def send(self, value: str | bytes) -> None:
        self.sent.append(value)


class FlowControlledFakeWebSocket(FakeWebSocket):
    def __init__(self) -> None:
        super().__init__()
        self.session: DeviceSession | None = None

    async def send(self, value: str | bytes) -> None:
        await super().send(value)
        if not isinstance(value, str) or self.session is None:
            return
        payload = json.loads(value)
        if payload["type"] == "speech_start":
            self.session.mark_speech_ready(payload["speech_id"])
        elif payload["type"] == "speech_end":
            self.session.mark_speech_playback_end(payload["speech_id"])


class FakeVlm:
    def __init__(self, response: str) -> None:
        self.response = response
        self.calls: list[tuple[str, object]] = []

    async def complete(
        self,
        system_prompt: str,
        prompt: str,
        image: str | None = None,
        video: VideoClip | None = None,
        examples: tuple[LlmMessage, ...] = (),
    ) -> str:
        del examples
        self.calls.append(
            (f"{system_prompt}\n\n{prompt}", image if video is None else video)
        )
        await asyncio.sleep(0)
        return self.response

    async def aclose(self) -> None:
        pass


class FakeProvider:
    def __init__(self) -> None:
        self.calls = 0

    async def stream_text(self, text_chunks, request):
        del request
        self.calls += 1
        async for text in text_chunks:
            yield b"ab"

    async def aclose(self) -> None:
        pass


class FlakyFirstAudioProvider(FakeProvider):
    async def stream_text(self, text_chunks, request):
        del request
        self.calls += 1
        async for _ in text_chunks:
            pass
        if self.calls == 1:
            raise ConnectionError("stale TTS connection")
        yield b"ab"


class FailingAudioStreamProvider(FakeProvider):
    async def stream_text(self, text_chunks, request):
        del request
        self.calls += 1
        async for _ in text_chunks:
            pass
        yield b"ab"
        raise ConnectionError("audio stream interrupted")


class FakeWebUi:
    def __init__(self) -> None:
        self.on_manual_analyze = None
        self.messages: list[dict[str, object]] = []

    async def start(self) -> None:
        pass

    async def close(self) -> None:
        pass

    async def publish(self, payload: dict[str, object]) -> None:
        self.messages.append(payload)

    async def capture_frame(self, trigger: str) -> str:
        assert trigger in {"sensor_event", "manual"}
        return "data:image/jpeg;base64,ZmFrZQ=="

    async def capture_video(self, trigger: str, window_seconds: float) -> VideoClip:
        assert trigger in {"sensor_event", "manual"}
        assert window_seconds == 1
        return VideoClip(b"fake video", format="mp4")


class FakeWebUiWithoutVideo(FakeWebUi):
    async def capture_video(
        self,
        trigger: str,
        window_seconds: float,
    ) -> VideoClip | None:
        del trigger, window_seconds
        return None


async def test_speech_output_retries_before_sending_first_audio() -> None:
    provider = FlakyFirstAudioProvider()
    output = SpeechOutput(provider, "test-voice", PcmFormat(), 0.5)
    socket = FakeWebSocket()
    session = DeviceSession(socket, device_id="test-device")

    await output.speak(session, "speech-retry", "我在这儿。")

    assert provider.calls == 2
    assert json.loads(socket.sent[0])["type"] == "speech_start"
    assert socket.sent[1] == b"ab"
    assert json.loads(socket.sent[2])["type"] == "speech_end"


async def test_speech_output_waits_for_device_playback_confirmation() -> None:
    provider = FakeProvider()
    output = SpeechOutput(provider, "test-voice", PcmFormat(), 0.5)
    socket = FlowControlledFakeWebSocket()
    session = DeviceSession(socket, device_id="test-device")
    socket.session = session
    session.configure_capabilities(["speech_ready", "speech_playback_end"])

    playback_confirmed = await output.speak(
        session,
        "speech-confirmed",
        "我在这儿。",
    )

    assert playback_confirmed is True
    assert json.loads(socket.sent[0])["type"] == "speech_start"
    assert socket.sent[1] == b"ab"
    assert json.loads(socket.sent[2])["type"] == "speech_end"


async def test_speech_output_does_not_retry_after_audio_started() -> None:
    provider = FailingAudioStreamProvider()
    output = SpeechOutput(provider, "test-voice", PcmFormat(), 0.5)
    socket = FakeWebSocket()
    session = DeviceSession(socket, device_id="test-device")

    try:
        await output.speak(session, "speech-interrupted", "我在这儿。")
    except ConnectionError:
        pass
    else:
        raise AssertionError("interrupted audio stream must fail")

    assert provider.calls == 1
    assert json.loads(socket.sent[0])["type"] == "speech_start"
    assert socket.sent[1] == b"ab"


async def test_ollama_client_sends_openai_multimodal_payload() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["model"] == "minicpm-v-4.6-local"
        assert body["stream"] is False
        assert body["reasoning_effort"] == "none"
        assert "response_format" not in body
        assert body["messages"][0]["role"] == "system"
        assert [message["role"] for message in body["messages"]] == [
            "system",
            "user",
            "assistant",
            "user",
        ]
        assert body["messages"][-1]["content"][1]["image_url"].startswith(
            "data:image/jpeg"
        )
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "{}"}}]},
            request=request,
        )

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    settings = Settings(vlm_model="minicpm-v-4.6-local")
    client = OllamaVlmClient(settings, client=http_client)
    await client.complete(
        "role",
        "observe",
        "data:image/jpeg;base64,ZmFrZQ==",
        examples=(
            LlmMessage("user", "sample input"),
            LlmMessage("assistant", "sample reply"),
        ),
    )
    await http_client.aclose()


async def test_llama_server_client_sends_raw_base64_video_payload() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        content = body["messages"][-1]["content"]
        assert body["model"] == "minicpm-v-4.6"
        assert body["stream"] is False
        assert body["messages"][0] == {"role": "system", "content": "role"}
        assert [message["role"] for message in body["messages"]] == [
            "system",
            "user",
            "assistant",
            "user",
        ]
        assert content[1]["type"] == "input_video"
        assert content[1]["input_video"]["data"] == "ZmFrZSB2aWRlbw=="
        assert content[1]["input_video"]["format"] == "mp4"
        assert not content[1]["input_video"]["data"].startswith("data:")
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "看到了视频"}}]},
            request=request,
        )

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    settings = Settings(
        vlm_provider="llama-server",
        vlm_base_url="http://127.0.0.1:8080/v1",
        vlm_model="minicpm-v-4.6",
    )
    client = LlamaServerVlmClient(settings, client=http_client)
    await client.complete(
        "role",
        "observe",
        video=VideoClip(b"fake video", format="mp4"),
        examples=(
            LlmMessage("user", "sample input"),
            LlmMessage("assistant", "sample reply"),
        ),
    )
    await http_client.aclose()


async def test_llama_server_client_uses_extended_response_budget() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        if body["max_tokens"] != 256:
            raise AssertionError(body["max_tokens"])
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "我在这儿。"}}]},
            request=request,
        )

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    settings = Settings(
        vlm_provider="llama-server",
        vlm_base_url="http://127.0.0.1:8080/v1",
        vlm_model="minicpm-v-4.6",
    )
    client = LlamaServerVlmClient(settings, client=http_client)
    await client.complete("role", "respond")
    await http_client.aclose()


async def test_vlm_event_uses_current_frame_and_existing_tts_chain(tmp_path) -> None:
    provider = FakeProvider()
    vlm = FakeVlm("嗯？突然这么黏人。")
    settings = Settings(
        runtime_mode="vlm",
        vlm_model="minicpm-v-4.6-local",
        log_dir=tmp_path,
    )
    webui = FakeWebUi()
    coordinator = VlmCoordinator(
        settings,
        provider,
        vlm,
        LocalLog(settings),
        webui,
        "test-voice",
        PcmFormat(),
    )
    socket = FakeWebSocket()
    session = DeviceSession(socket, device_id="test-device")

    await coordinator.on_event(
        session,
        PhysicalEvent(event_id="evt-1", event="touch", behavior="happy"),
    )
    task = coordinator._active_task
    assert task is not None
    await task

    assert json.loads(socket.sent[0]) == {
        "type": "motion_ack",
        "event_id": "evt-1",
        "will_speak": True,
    }
    assert json.loads(socket.sent[1])["type"] == "speech_start"
    assert json.loads(socket.sent[-1])["type"] == "speech_end"
    next(
        message
        for message in webui.messages
        if message["type"] == "inference_result"
    )
    assert provider.calls == 1
    await coordinator.aclose()


async def test_llama_server_vlm_event_uses_recent_video_and_existing_tts_chain(
    tmp_path,
) -> None:
    provider = FakeProvider()
    vlm = FakeVlm("慢点，我都快站不稳了。")
    settings = Settings(
        runtime_mode="vlm",
        vlm_provider="llama-server",
        vlm_model="minicpm-v-4.6",
        log_dir=tmp_path,
    )
    webui = FakeWebUi()
    coordinator = VlmCoordinator(
        settings,
        provider,
        vlm,
        LocalLog(settings),
        webui,
        "test-voice",
        PcmFormat(),
    )
    socket = FakeWebSocket()
    session = DeviceSession(socket, device_id="test-device")

    await coordinator.on_event(
        session,
        PhysicalEvent(event_id="evt-video", event="touch", behavior="happy"),
    )
    task = coordinator._active_task
    assert task is not None
    await task

    assert isinstance(vlm.calls[0][1], VideoClip)
    assert vlm.calls[0][1].data == b"fake video"
    assert vlm.calls[0][1].format == "mp4"
    next(
        message
        for message in webui.messages
        if message["type"] == "inference_result"
    )
    assert provider.calls == 1
    await coordinator.aclose()


async def test_vlm_ignores_stationary_low_confidence_event(tmp_path) -> None:
    settings = Settings(
        runtime_mode="vlm",
        vlm_provider="llama-server",
        vlm_model="minicpm-v-4.6",
        log_dir=tmp_path,
    )
    vlm = FakeVlm("我在这儿")
    webui = FakeWebUi()
    coordinator = VlmCoordinator(
        settings,
        FakeProvider(),
        vlm,
        LocalLog(settings),
        webui,
        "test-voice",
        PcmFormat(),
    )
    socket = FakeWebSocket()
    session = DeviceSession(socket, device_id="test-device")
    event = PhysicalEvent(
        event_id="evt-stationary",
        event="shaking",
        behavior="dizzy",
        intensity=0.0,
        summary=MotionSummary(
            confidence=0.31,
            motion_duration_ms=0,
            peak_angular_speed_dps=0.0,
            peak_dynamic_acceleration_g=0.0,
            tilt_strength=0.02,
        ),
    )

    await coordinator.on_event(session, event)

    if vlm.calls:
        raise AssertionError("stationary event must not call VLM")
    if json.loads(socket.sent[-1]) != {
        "type": "motion_ack",
        "event_id": "evt-stationary",
        "will_speak": False,
    }:
        raise AssertionError(socket.sent[-1])
    await coordinator.aclose()


async def test_llama_server_skips_model_when_video_is_unavailable(tmp_path) -> None:
    settings = Settings(
        runtime_mode="vlm",
        vlm_provider="llama-server",
        vlm_model="minicpm-v-4.6",
        log_dir=tmp_path,
    )
    vlm = FakeVlm("我在这儿")
    webui = FakeWebUiWithoutVideo()
    coordinator = VlmCoordinator(
        settings,
        FakeProvider(),
        vlm,
        LocalLog(settings),
        webui,
        "test-voice",
        PcmFormat(),
    )

    await coordinator.manual_analyze()
    task = coordinator._active_task
    assert task is not None
    await task

    assert vlm.calls == []
    assert any(message["type"] == "inference_error" for message in webui.messages)
    await coordinator.aclose()


async def test_manual_vlm_analysis_does_not_require_esp32(tmp_path) -> None:
    settings = Settings(
        runtime_mode="vlm",
        vlm_model="minicpm-v-4.6-local",
        log_dir=tmp_path,
    )
    webui = FakeWebUi()
    coordinator = VlmCoordinator(
        settings,
        FakeProvider(),
        FakeVlm("忙你的吧，我在这儿。"),
        LocalLog(settings),
        webui,
        "test-voice",
        PcmFormat(),
    )

    await coordinator.manual_analyze()
    task = coordinator._active_task
    assert task is not None
    await task

    next(message for message in webui.messages if message["type"] == "inference_result")
    await coordinator.aclose()


async def test_manual_vlm_speech_does_not_reuse_last_sensor_event(tmp_path) -> None:
    settings = Settings(
        runtime_mode="vlm",
        vlm_model="minicpm-v-4.6-local",
        log_dir=tmp_path,
    )
    provider = FakeProvider()
    vlm = FakeVlm("嗯？突然这么黏人。")
    webui = FakeWebUi()
    coordinator = VlmCoordinator(
        settings,
        provider,
        vlm,
        LocalLog(settings),
        webui,
        "test-voice",
        PcmFormat(),
    )
    socket = FakeWebSocket()
    session = DeviceSession(socket, device_id="test-device")

    await coordinator.on_event(
        session,
        PhysicalEvent(event_id="evt-old", event="touch", behavior="happy"),
    )
    event_task = coordinator._active_task
    assert event_task is not None
    await event_task

    socket.sent.clear()
    vlm.response = "忙你的吧，我在这儿。"
    await coordinator.manual_analyze()
    manual_task = coordinator._active_task
    assert manual_task is not None
    await manual_task

    control_frames = [
        json.loads(message) for message in socket.sent if isinstance(message, str)
    ]
    speech_start = next(
        message for message in control_frames if message["type"] == "speech_start"
    )
    assert speech_start["event_id"] == ""
    await coordinator.aclose()
