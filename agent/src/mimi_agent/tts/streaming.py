"""Helpers for preserving the first-audio streaming boundary."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable

from mimi_agent.audio.pcm import PcmFormat, validate_pcm_chunk


async def validated_stream(
    source: AsyncIterator[bytes],
    audio_format: PcmFormat,
    on_first_chunk: Callable[[], Awaitable[None]] | None = None,
) -> AsyncIterator[bytes]:
    """Validate PCM alignment while yielding each chunk immediately."""

    first = True
    pending = b""
    async for chunk in source:
        if not chunk:
            continue
        combined = pending + chunk
        aligned_length = len(combined) - len(combined) % audio_format.frame_bytes
        if aligned_length:
            aligned = combined[:aligned_length]
            validate_pcm_chunk(aligned, audio_format)
            if first and on_first_chunk is not None:
                await on_first_chunk()
            first = False
            yield aligned
        pending = combined[aligned_length:]

    if pending:
        raise ValueError("PCM stream ended with an incomplete audio frame")
