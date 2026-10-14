"""Shared types and response handling for local vision-model providers."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from mimi_agent.agent_core.llm import LlmMessage


class VlmProviderError(RuntimeError):
    """Raised when the local VLM cannot produce a response."""


@dataclass(frozen=True)
class VideoClip:
    """A short browser-captured clip ready for a local VLM request."""

    data: bytes
    format: str = "auto"


class VlmClient(Protocol):
    async def complete(
        self,
        system_prompt: str,
        prompt: str,
        image: str | None = None,
        video: VideoClip | None = None,
        examples: tuple[LlmMessage, ...] = (),
    ) -> str:
        """Return the complete assistant text for one multimodal request."""

    async def aclose(self) -> None:
        """Close reusable provider resources."""


def response_text(payload: object) -> str:
    if not isinstance(payload, Mapping):
        raise VlmProviderError("VLM response is not an object")
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise VlmProviderError("VLM response has no choices")
    choice = choices[0]
    if not isinstance(choice, Mapping):
        raise VlmProviderError("VLM response choice is invalid")
    message = choice.get("message")
    if not isinstance(message, Mapping):
        raise VlmProviderError("VLM response message is invalid")
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, Mapping) and isinstance(item.get("text"), str):
                parts.append(item["text"])
        return "".join(parts)
    raise VlmProviderError("VLM response content is not text")


def response_diagnostics(payload: object) -> str:
    if not isinstance(payload, Mapping):
        return "response is not an object"
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return f"top-level keys={sorted(payload.keys())}"
    choice = choices[0]
    if not isinstance(choice, Mapping):
        return "first choice is not an object"
    message = choice.get("message")
    if not isinstance(message, Mapping):
        return f"choice keys={sorted(choice.keys())}"
    alternatives = [
        name
        for name in ("reasoning", "reasoning_content")
        if message.get(name)
    ]
    suffix = f", alternatives={alternatives}" if alternatives else ""
    return (
        f"message keys={sorted(message.keys())}, "
        f"finish_reason={choice.get('finish_reason')!r}{suffix}"
    )
