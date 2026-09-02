import asyncio

from mimi_agent.tts.text_chunker import TextChunker


async def test_text_chunker_preserves_all_text_and_comma_chunks() -> None:
    async def deltas():
        yield "别晃啦"
        yield "，"
        yield "我真的要晕了！"

    chunks = [chunk async for chunk in TextChunker().stream(deltas())]
    assert chunks == ["别晃啦，", "我真的要晕了！"]
    assert "".join(chunks) == "别晃啦，我真的要晕了！"


async def test_text_chunker_flushes_without_cancelling_slow_source() -> None:
    async def deltas():
        yield "你好呀"
        await asyncio.sleep(0.03)
        yield "，我还在这里。"

    chunks = [
        chunk
        async for chunk in TextChunker(
            first_min_chars=3,
            chunk_min_chars=8,
            flush_interval_seconds=0.005,
            max_wait_seconds=0.01,
        ).stream(deltas())
    ]
    assert "".join(chunks) == "你好呀，我还在这里。"
    assert chunks[0] == "你好呀"
