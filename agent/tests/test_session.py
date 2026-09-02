import pytest

from mimi_agent.device.session import (
    MAX_DEVICE_AUDIO_FRAME_BYTES,
    DeviceSession,
)


class FakeWebSocket:
    def __init__(self) -> None:
        self.sent: list[bytes] = []

    async def send(self, value: bytes) -> None:
        self.sent.append(value)


async def test_send_audio_splits_large_pcm_without_interleaving() -> None:
    socket = FakeWebSocket()
    session = DeviceSession(socket)
    pcm = bytes(range(256)) * 50

    await session.send_audio(pcm)

    assert b"".join(socket.sent) == pcm
    assert all(0 < len(frame) <= MAX_DEVICE_AUDIO_FRAME_BYTES for frame in socket.sent)
    assert all(len(frame) % 2 == 0 for frame in socket.sent)


async def test_send_audio_rejects_incomplete_pcm_sample() -> None:
    session = DeviceSession(FakeWebSocket())

    with pytest.raises(ValueError, match="16-bit samples"):
        await session.send_audio(b"odd")
