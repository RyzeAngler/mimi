"""Provider-neutral streaming TTS contract."""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, Protocol

from mimi_agent.audio.pcm import PcmFormat


@dataclass(frozen=True)
class TtsRequest:
    voice: str
    audio_format: PcmFormat = PcmFormat()
    speed_ratio: float = 1.0
    volume_ratio: float = 1.0
    uid: str = "mimi-device"
    additions: dict[str, Any] | None = None

    def validate(self) -> None:
        if not self.voice.strip():
            raise ValueError("TTS voice cannot be empty")
        if not 0.5 <= self.speed_ratio <= 2.0:
            raise ValueError("TTS speed ratio must be between 0.5 and 2.0")
        if not 0.5 <= self.volume_ratio <= 2.0:
            raise ValueError("TTS volume ratio must be between 0.5 and 2.0")
        self.audio_format.validate()


class TtsProvider(Protocol):
    def stream_text(
        self,
        text_chunks: AsyncIterator[str],
        request: TtsRequest,
    ) -> AsyncIterator[bytes]:
        """Consume one text session and yield PCM as soon as it is available."""

    async def aclose(self) -> None:
        """Close persistent provider resources."""
