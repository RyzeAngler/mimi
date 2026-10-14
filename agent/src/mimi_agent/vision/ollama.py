"""Ollama client through its OpenAI-compatible chat completions API."""

import logging
from typing import Any

import httpx

from mimi_agent.agent_core.llm import LlmMessage
from mimi_agent.config import Settings

from .client import (
    VideoClip,
    VlmClient,
    VlmProviderError,
    response_diagnostics,
    response_text,
)

logger = logging.getLogger(__name__)


class OllamaVlmClient:
    """Call an Ollama model without making the browser talk to Ollama directly."""

    def __init__(
        self,
        settings: Settings,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.settings = settings
        self._client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(settings.vlm_request_timeout_seconds),
            trust_env=False,
            limits=httpx.Limits(
                max_connections=1,
                max_keepalive_connections=1,
                keepalive_expiry=60.0,
            ),
        )
        self._owns_client = client is None

    def _body(
        self,
        system_prompt: str,
        prompt: str,
        image: str | None,
        examples: tuple[LlmMessage, ...],
    ) -> dict[str, Any]:
        content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
        if image is not None:
            content.append(
                {
                    "type": "image_url",
                    "image_url": image,
                }
            )
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt}
        ]
        messages.extend(
            {"role": message.role, "content": message.content}
            for message in examples
        )
        messages.append({"role": "user", "content": content})
        return {
            "model": self.settings.vlm_model,
            "messages": messages,
            "stream": False,
            "temperature": 0.2,
            "max_tokens": self.settings.vlm_max_tokens,
            "reasoning_effort": "none",
        }

    async def complete(
        self,
        system_prompt: str,
        prompt: str,
        image: str | None = None,
        video: VideoClip | None = None,
        examples: tuple[LlmMessage, ...] = (),
    ) -> str:
        self.settings.validate_vlm()
        if video is not None:
            raise VlmProviderError("当前 Ollama provider 不支持视频输入")
        logger.info(
            f"VLM request started provider=ollama model={self.settings.vlm_model} "
            f"image={image is not None}"
        )
        try:
            response = await self._client.post(
                f"{self.settings.vlm_base_url}/chat/completions",
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                json=self._body(system_prompt, prompt, image, examples),
            )
            if response.status_code >= 400:
                detail = response.text[:500]
                raise VlmProviderError(
                    f"Ollama HTTP {response.status_code}: {detail}"
                )
            try:
                payload = response.json()
            except ValueError as exc:
                raise VlmProviderError("Ollama returned invalid JSON") from exc
            text = response_text(payload)
            if not text.strip():
                raise VlmProviderError(
                    "Ollama returned empty text ("
                    f"{response_diagnostics(payload)})"
                )
            logger.info(
                f"VLM request completed provider=ollama model={self.settings.vlm_model} "
                f"chars={len(text)}"
            )
            return text
        except httpx.HTTPError as exc:
            raise VlmProviderError(f"Ollama transport failed: {exc}") from exc

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()
