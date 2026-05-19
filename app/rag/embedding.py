from app.llm.deepseek import DeepSeekLLM


async def embed_chunks(chunks: list[dict]) -> list[list[float]]:
    llm = DeepSeekLLM()
    texts = [c["text"] for c in chunks]
    return await llm.embed(texts)
