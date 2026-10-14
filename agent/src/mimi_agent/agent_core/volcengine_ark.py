"""Volcengine Ark Chat Completions client in SSE streaming mode."""

import json
import logging
from collections.abc import AsyncIterator
from typing import Any

import httpx

from mimi_agent.config import Settings

from .llm import LlmClient, LlmMessage, LlmSpeechRequest

logger = logging.getLogger(__name__)


class LlmProviderError(RuntimeError):
    """Raised when Ark cannot produce a complete response."""


class VolcengineArkClient(LlmClient):
    def __init__(
        self,
        settings: Settings,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.settings = settings
        self._client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(settings.ark_timeout_seconds),
            trust_env=False,
            limits=httpx.Limits(
                max_connections=4,
                max_keepalive_connections=2,
                keepalive_expiry=60.0,
            ),
        )
        self._owns_client = client is None

    def _body(self, request: LlmSpeechRequest) -> dict[str, Any]:
        if (
            not request.messages
            or request.messages[0].role != "system"
            or request.messages[-1].role != "user"
        ):
            raise LlmProviderError(
                "LLM request must contain a system prompt and end with the current user prompt"
            )
        body: dict[str, Any] = {
            "model": self.settings.ark_model,
            "messages": [
                _message_payload(message)
                for message in request.messages
            ],
            "stream": True,
            "temperature": self.settings.ark_temperature,
            "max_tokens": self.settings.ark_max_tokens,
            "thinking": {"type": "disabled"},
        }
        if self.settings.ark_service_tier:
            body["service_tier"] = self.settings.ark_service_tier
        return body

    async def stream_reply(
        self, request: LlmSpeechRequest
    ) -> AsyncIterator[str]:
        """Stream only assistant text deltas from Ark's SSE response."""

        self.settings.validate_llm()
        logger.info(
            f"LLM request started provider=volcengine_ark "
            f"model={self.settings.ark_model} event={request.event} "
            f"behavior={request.behavior} intensity={request.intensity:.3f} "
            "mode=streaming"
        )
        try:
            async with self._client.stream(
                "POST",
                f"{self.settings.ark_base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.settings.ark_api_key}",
                    "Content-Type": "application/json",
                    "Accept": "text/event-stream",
                },
                json=self._body(request),
            ) as response:
                if response.status_code >= 400:
                    detail = (await response.aread()).decode(
                        "utf-8", errors="replace"
                    )
                    raise LlmProviderError(
                        f"Ark HTTP {response.status_code}: {detail[:500]}"
                    )

                completed = False
                yielded = False
                total_chars = 0
                async for line in response.aiter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    payload = line[5:].strip()
                    if payload == "[DONE]":
                        completed = True
                        break
                    try:
                        message = json.loads(payload)
                    except json.JSONDecodeError as exc:
                        raise LlmProviderError(
                            "Ark returned invalid streaming JSON"
                        ) from exc
                    if not isinstance(message, dict):
                        raise LlmProviderError(
                            "Ark returned a non-object streaming response"
                        )
                    if error := message.get("error"):
                        raise LlmProviderError(f"Ark request failed: {error}")
                    delta = _stream_text_delta(message)
                    if delta:
                        yielded = True
                        total_chars += len(delta)
                        yield delta

                if not completed:
                    raise LlmProviderError(
                        "Ark stream ended before the completion marker"
                    )
                if not yielded:
                    raise LlmProviderError("Ark returned empty streamed text")
                logger.info(
                    f"LLM stream completed provider=volcengine_ark "
                    f"model={self.settings.ark_model} chars={total_chars}"
                )
        except httpx.HTTPError as exc:
            raise LlmProviderError(f"Ark transport failed: {exc}") from exc

    async def aclose(self) -> None:
        """Close the reusable HTTP client owned by this provider."""

        if self._owns_client:
            await self._client.aclose()


def _stream_text_delta(message: dict[str, Any]) -> str:
    choices = message.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    choice = choices[0]
    if not isinstance(choice, dict):
        raise LlmProviderError("Ark streaming choice is invalid")
    delta = choice.get("delta")
    if delta is None:
        return ""
    if not isinstance(delta, dict):
        raise LlmProviderError("Ark streaming delta is invalid")
    content = delta.get("content")
    if content is None:
        return ""
    if not isinstance(content, str):
        raise LlmProviderError("Ark streaming content is not plain text")
    return content


def _message_payload(message: LlmMessage) -> dict[str, Any]:
    return {"role": message.role, "content": message.content}
