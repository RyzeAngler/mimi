"""Bounded-latency text segmentation for a single TTS session."""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator


class TextChunker:
    """Yield complete, ordered text chunks without dropping punctuation or tails."""

    _STRONG = frozenset("。！？!?；;\n")
    _WEAK = frozenset("，,、：:")

    def __init__(
        self,
        *,
        first_min_chars: int = 4,
        chunk_min_chars: int = 8,
        chunk_max_chars: int = 18,
        flush_interval_seconds: float = 0.12,
        max_wait_seconds: float = 0.28,
    ) -> None:
        if not 1 <= first_min_chars <= chunk_min_chars <= chunk_max_chars:
            raise ValueError("TextChunker character limits are invalid")
        if flush_interval_seconds <= 0 or max_wait_seconds <= 0:
            raise ValueError("TextChunker timers must be positive")
        self.first_min_chars = first_min_chars
        self.chunk_min_chars = chunk_min_chars
        self.chunk_max_chars = chunk_max_chars
        self.flush_interval_seconds = flush_interval_seconds
        self.max_wait_seconds = max_wait_seconds

    async def stream(self, deltas: AsyncIterator[str]) -> AsyncIterator[str]:
        iterator = deltas.__aiter__()
        pending = ""
        pending_started_at: float | None = None
        first_chunk = True
        next_delta: asyncio.Task[str] | None = None

        while True:
            if next_delta is None:
                next_delta = asyncio.create_task(anext(iterator))
            try:
                done, _ = await asyncio.wait(
                    {next_delta}, timeout=self._timeout(pending_started_at)
                )
            except asyncio.CancelledError:
                next_delta.cancel()
                with contextlib.suppress(BaseException):
                    await next_delta
                raise
            if not done:
                if pending and len(pending) >= self.first_min_chars:
                    yield pending
                    pending = ""
                    pending_started_at = None
                    first_chunk = False
                continue

            try:
                delta = next_delta.result()
            except StopAsyncIteration:
                break
            finally:
                next_delta = None

            if not delta:
                continue
            if pending_started_at is None:
                pending_started_at = asyncio.get_running_loop().time()
            pending += delta

            while True:
                boundary = self._boundary(pending, first_chunk)
                if boundary is None:
                    break
                yield pending[:boundary]
                pending = pending[boundary:]
                pending_started_at = (
                    asyncio.get_running_loop().time() if pending else None
                )
                first_chunk = False

            while len(pending) >= self.chunk_max_chars:
                yield pending[: self.chunk_max_chars]
                pending = pending[self.chunk_max_chars :]
                pending_started_at = (
                    asyncio.get_running_loop().time() if pending else None
                )
                first_chunk = False

        if pending:
            yield pending

    def _timeout(self, pending_started_at: float | None) -> float:
        if pending_started_at is None:
            return self.max_wait_seconds
        elapsed = asyncio.get_running_loop().time() - pending_started_at
        return max(0.001, min(self.flush_interval_seconds, self.max_wait_seconds - elapsed))

    def _boundary(self, text: str, first_chunk: bool) -> int | None:
        minimum = self.first_min_chars if first_chunk else self.chunk_min_chars
        for index, char in enumerate(text):
            length = index + 1
            if char in self._STRONG and length >= minimum:
                return length
            if char in self._WEAK and length >= minimum:
                return length
        return None
