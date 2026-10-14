"""Provider-neutral streaming LLM boundary for short Mimi speech turns."""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Literal, Protocol

from mimi_agent.protocol.messages import MotionSummary, PhysicalEvent


@dataclass(frozen=True)
class LlmMessage:
    """One chat message sent to the LLM provider."""

    role: Literal["system", "user", "assistant"]
    content: str


@dataclass(frozen=True)
class LlmSpeechRequest:
    event: str
    behavior: str
    intensity: float
    summary: MotionSummary | None
    messages: tuple[LlmMessage, ...]

    @property
    def current_prompt(self) -> str:
        if not self.messages or self.messages[-1].role != "user":
            raise ValueError("LLM request must end with the current user prompt")
        return self.messages[-1].content

    @classmethod
    def from_event(
        cls, event: PhysicalEvent, messages: tuple[LlmMessage, ...]
    ) -> "LlmSpeechRequest":
        return cls(
            event=event.event,
            behavior=event.behavior,
            intensity=event.intensity,
            summary=event.summary,
            messages=messages,
        )


class LlmClient(Protocol):
    def stream_reply(self, request: LlmSpeechRequest) -> AsyncIterator[str]:
        """Yield plain-text deltas until the provider marks the response done."""

    async def aclose(self) -> None:
        """Close the reusable HTTP client."""
