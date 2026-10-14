"""llama-server client for OpenAI-compatible image and video requests."""

import base64
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


class LlamaServerVlmClient:
    """Call llama-server's multimodal OpenAI-compatible endpoint."""

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
        video: VideoClip | None,
        examples: tuple[LlmMessage, ...],
    ) -> dict[str, Any]:
        if image is not None and video is not None:
            raise VlmProviderError("一次请求不能同时发送图片和视频")
        content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
        if image is not None:
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": image},
                }
            )
        if video is not None:
            content.append(
                {
                    "type": "input_video",
                    "input_video": {
                        "data": base64.b64encode(video.data).decode("ascii"),
                        "format": video.format,
                    },
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
        if video is None and image is None:
            media = "none"
        elif video is not None:
            media = f"video:{len(video.data)} bytes format={video.format}"
        else:
            media = "image"
        logger.info(
            f"VLM request started provider=llama-server "
            f"model={self.settings.vlm_model} media={media}"
        )
        try:
            response = await self._client.post(
                f"{self.settings.vlm_base_url}/chat/completions",
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                json=self._body(system_prompt, prompt, image, video, examples),
            )
            if response.status_code >= 400:
                detail = response.text[:500]
                raise VlmProviderError(
                    f"llama-server HTTP {response.status_code}: {detail}"
                )
            try:
                payload = response.json()
            except ValueError as exc:
                raise VlmProviderError("llama-server returned invalid JSON") from exc
            text = response_text(payload)
            if not text.strip():
                raise VlmProviderError(
                    "llama-server returned empty text ("
                    f"{response_diagnostics(payload)})"
                )
            logger.info(
                f"VLM request completed provider=llama-server "
                f"model={self.settings.vlm_model} chars={len(text)}"
            )
            return text
        except httpx.HTTPError as exc:
            raise VlmProviderError(f"llama-server transport failed: {exc}") from exc

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()
