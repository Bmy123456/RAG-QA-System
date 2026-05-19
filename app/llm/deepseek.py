import asyncio
from typing import AsyncIterator
from openai import AsyncOpenAI
from app.llm.base import BaseLLM
from app.config import get_config

config = get_config()


class DeepSeekLLM(BaseLLM):
    def __init__(self):
        self.client = AsyncOpenAI(
            api_key=config["llm"]["api_key"],
            base_url=config["llm"]["base_url"],
        )
        self.model = config["llm"]["model"]
        self.embed_model = config["embedding"]["model"]

    async def chat_stream(self, messages: list[dict]) -> AsyncIterator[str]:
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            stream=True,
            temperature=0.3,
        )
        async for chunk in response:
            delta = chunk.choices[0].delta
            if delta.content:
                yield delta.content

    async def embed(self, texts: list[str]) -> list[list[float]]:
        response = await self.client.embeddings.create(
            model=self.embed_model,
            input=texts,
        )
        return [d.embedding for d in response.data]


class DeepSeekReranker:
    def __init__(self, llm: DeepSeekLLM):
        self.llm = llm

    async def rerank(self, query: str, documents: list[str]) -> list[tuple[int, float]]:
        async def score_one(idx: int, doc: str) -> tuple[int, float]:
            messages = [
                {"role": "system", "content": "Rate the relevance of this document to the query on a scale of 0 to 10. Reply with only a number."},
                {"role": "user", "content": f"Query: {query}\n\nDocument: {doc[:2000]}\n\nRelevance score (0-10):"},
            ]
            raw = ""
            async for chunk in self.llm.chat_stream(messages):
                raw += chunk
            try:
                score = float(raw.strip()) / 10.0
            except ValueError:
                score = 0.0
            return idx, score

        results = await asyncio.gather(*[score_one(i, doc) for i, doc in enumerate(documents)])
        results.sort(key=lambda x: x[1], reverse=True)
        return results
