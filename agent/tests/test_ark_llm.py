import json

import httpx

from mimi_agent.agent_core.llm import (
    LlmMessage,
    LlmSpeechRequest,
)
from mimi_agent.agent_core.volcengine_ark import VolcengineArkClient
from mimi_agent.config import Settings
from mimi_agent.protocol.messages import MotionSummary


async def test_ark_streams_plain_text_deltas_until_done() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["stream"] is True
        assert body["thinking"] == {"type": "disabled"}
        assert body["max_tokens"] == 24
        assert body["messages"] == [
            {"role": "system", "content": "你是 Mimi。"},
            {"role": "user", "content": "当前动作是被触摸。"},
        ]
        assert request.headers["Accept"] == "text/event-stream"
        payload = b"\n".join(
            [
                'data: {"choices":[{"delta":{"content":"别晃啦，"}}]}'.encode(),
                'data: {"choices":[{"delta":{"content":"我真的要晕了！"}}]}'.encode(),
                b"data: [DONE]",
                b"",
            ]
        )
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=payload,
            request=request,
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    llm = VolcengineArkClient(
        Settings(ark_api_key="ark-key", ark_model="fast-model"), client=client
    )
    chunks = [
        chunk
        async for chunk in llm.stream_reply(
            LlmSpeechRequest(
                "shaking",
                "dizzy",
                0.8,
                MotionSummary(confidence=0.9),
                (
                    LlmMessage("system", "你是 Mimi。"),
                    LlmMessage("user", "当前动作是被触摸。"),
                ),
            )
        )
    ]
    await client.aclose()
    assert chunks == ["别晃啦，", "我真的要晕了！"]

