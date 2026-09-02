"""Raw PCM contract shared by TTS output and the ESP32 audio player."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass


@dataclass(frozen=True)
class PcmFormat:
    sample_rate: int = 16000
    channels: int = 1
    sample_width: int = 2

    @property
    def frame_bytes(self) -> int:
        return self.channels * self.sample_width

    @property
    def name(self) -> str:
        bits = self.sample_width * 8
        return f"pcm_s{bits}le"

    def validate(self) -> None:
        if self.sample_rate <= 0:
            raise ValueError("sample_rate must be positive")
        if self.channels != 1:
            raise ValueError("Mimi v1 audio contract is mono PCM")
        if self.sample_width != 2:
            raise ValueError("Mimi v1 audio contract is 16-bit PCM")


def validate_pcm_chunk(chunk: bytes, audio_format: PcmFormat) -> bytes:
    audio_format.validate()
    if len(chunk) % audio_format.frame_bytes:
        raise ValueError(
            f"PCM chunk has {len(chunk)} bytes; it is not aligned to "
            f"{audio_format.frame_bytes}-byte audio frames"
        )
    return chunk


def iter_bytes(data: bytes, chunk_size: int = 1024) -> Iterator[bytes]:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    for offset in range(0, len(data), chunk_size):
        yield data[offset : offset + chunk_size]

