"""
重排序模块：对初步召回的文档进行精排，提升检索精度。

支持：
- 跨编码器：bge-reranker（本地）、Cohere Rerank API（云端）
- LLM 评分：Pointwise（逐个评分）、Pairwise（两两比较）

输入兼容 RetrievalResult 和 SearchResult 两种格式。
"""

from __future__ import annotations

import asyncio
import json
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any


# ---------------------------------------------------------------------------
# 数据类
# ---------------------------------------------------------------------------

@dataclass
class RerankInput:
    """统一的输入格式"""
    chunk_id: str
    content: str
    metadata: dict
    original_score: float

    @staticmethod
    def from_retrieval_result(r) -> RerankInput:
        return RerankInput(
            chunk_id=r.chunk_id,
            content=r.content,
            metadata=r.metadata,
            original_score=r.score,
        )

    @staticmethod
    def from_search_result(r) -> RerankInput:
        return RerankInput(
            chunk_id=r.chunk_id,
            content=r.text,
            metadata=r.metadata,
            original_score=r.score,
        )

    @staticmethod
    def from_chunk(c, score: float = 0.0) -> RerankInput:
        """从 ingestion.Chunk 转换"""
        meta = {}
        if hasattr(c.metadata, "__dataclass_fields__"):
            meta = {k: v for k, v in c.metadata.__dict__.items() if v is not None}
        elif isinstance(c.metadata, dict):
            meta = c.metadata
        return RerankInput(
            chunk_id=c.chunk_id,
            content=c.text,
            metadata=meta,
            original_score=score,
        )


@dataclass
class RerankResult:
    """重排序结果"""
    chunk_id: str
    content: str
    metadata: dict
    score: float            # reranker 打分（0~1）
    original_score: float   # 原始检索分数


# ---------------------------------------------------------------------------
# 抽象基类
# ---------------------------------------------------------------------------

class BaseReranker(ABC):
    """重排序器抽象基类。"""

    @abstractmethod
    async def rerank(
        self,
        query: str,
        documents: list[RerankInput],
        top_k: int = 5,
    ) -> list[RerankResult]:
        """对候选文档重排序并截断到 top_k。

        参数:
            query:     查询文本
            documents: 候选文档列表
            top_k:     返回数量

        返回:
            list[RerankResult]，按 score 降序，长度 <= top_k
        """
        ...

    @property
    @abstractmethod
    def model_name(self) -> str:
        """模型标识"""
        ...


# ===========================================================================
# 跨编码器：bge-reranker（本地）
# ===========================================================================

class BgeReranker(BaseReranker):
    """本地 bge-reranker 跨编码器模型。

    使用 sentence-transformers CrossEncoder 推理，线程池避免阻塞。
    """

    def __init__(
        self,
        model_name: str = "BAAI/bge-reranker-v2-m3",
        device: str = "cpu",
        max_workers: int = 2,
    ):
        self._model_name = model_name
        self._device = device
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._model = None  # 延迟加载

    def _load_model(self):
        if self._model is None:
            from sentence_transformers import CrossEncoder
            self._model = CrossEncoder(self._model_name, max_length=512, device=self._device)

    @property
    def model_name(self) -> str:
        return self._model_name

    async def rerank(
        self,
        query: str,
        documents: list[RerankInput],
        top_k: int = 5,
    ) -> list[RerankResult]:
        if not documents:
            return []

        loop = asyncio.get_event_loop()
        results = await loop.run_in_executor(
            self._executor, self._sync_rerank, query, documents, top_k,
        )
        return results

    def _sync_rerank(
        self,
        query: str,
        documents: list[RerankInput],
        top_k: int,
    ) -> list[RerankResult]:
        self._load_model()

        pairs = [(query, doc.content[:2048]) for doc in documents]
        scores = self._model.predict(pairs)

        # sigmoid 归一化到 0~1
        import math
        norm_scores = [1 / (1 + math.exp(-s)) for s in scores]

        scored = list(zip(documents, norm_scores))
        scored.sort(key=lambda x: x[1], reverse=True)

        return [
            RerankResult(
                chunk_id=doc.chunk_id,
                content=doc.content,
                metadata=doc.metadata,
                score=float(score),
                original_score=doc.original_score,
            )
            for doc, score in scored[:top_k]
        ]


# ===========================================================================
# 跨编码器：Cohere Rerank API（云端）
# ===========================================================================

class CohereReranker(BaseReranker):
    """Cohere Rerank API 云端重排序。"""

    def __init__(
        self,
        api_key: str,
        model: str = "rerank-multilingual-v3.0",
        top_n: int = 5,
    ):
        self._api_key = api_key
        self._model = model

    @property
    def model_name(self) -> str:
        return f"cohere/{self._model}"

    async def rerank(
        self,
        query: str,
        documents: list[RerankInput],
        top_k: int = 5,
    ) -> list[RerankResult]:
        if not documents:
            return []

        import cohere

        client = cohere.AsyncClient(api_key=self._api_key)

        docs_text = [doc.content[:4096] for doc in documents]
        response = await client.rerank(
            model=self._model,
            query=query,
            documents=docs_text,
            top_n=min(top_k, len(documents)),
        )

        results: list[RerankResult] = []
        for item in response.results:
            doc = documents[item.index]
            results.append(RerankResult(
                chunk_id=doc.chunk_id,
                content=doc.content,
                metadata=doc.metadata,
                score=item.relevance_score,
                original_score=doc.original_score,
            ))

        return results


# 修正拼写错误
# ===========================================================================
# LLM 评分：Pointwise（逐个评分）
# ===========================================================================

class LLMPointwiseReranker(BaseReranker):
    """基于 LLM 的逐个评分重排序。

    让 LLM 对每个文档独立打 0-10 分，然后归一化到 0~1。
    调用次数 = N（文档数），适合文档数适中的场景。
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.deepseek.com/v1",
        model: str = "deepseek-chat",
        max_concurrency: int = 5,
    ):
        from openai import AsyncOpenAI
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        self._model = model
        self._semaphore = asyncio.Semaphore(max_concurrency)

    @property
    def model_name(self) -> str:
        return self._model

    async def rerank(
        self,
        query: str,
        documents: list[RerankInput],
        top_k: int = 5,
    ) -> list[RerankResult]:
        if not documents:
            return []

        async def _score_one(doc: RerankInput) -> tuple[RerankInput, float]:
            async with self._semaphore:
                prompt = f"""请评估以下文档与查询的相关性，给出 0-10 的整数分数。
0 表示完全无关，10 表示高度相关。

查询：{query}

文档：{doc.content[:2000]}

请只输出一个整数分数，不要输出其他内容。"""

                messages = [
                    {"role": "system", "content": "你是一个文档相关性评估助手。只输出一个 0-10 的整数分数。"},
                    {"role": "user", "content": prompt},
                ]

                try:
                    resp = await self._client.chat.completions.create(
                        model=self._model, messages=messages, temperature=0, max_tokens=10,
                    )
                    raw = resp.choices[0].message.content.strip()
                    score = float(raw) / 10.0
                    score = max(0.0, min(1.0, score))
                except (ValueError, Exception):
                    score = doc.original_score

                return doc, score

        tasks = [_score_one(doc) for doc in documents]
        results = await asyncio.gather(*tasks)

        scored = list(results)
        scored.sort(key=lambda x: x[1], reverse=True)

        return [
            RerankResult(
                chunk_id=doc.chunk_id,
                content=doc.content,
                metadata=doc.metadata,
                score=score,
                original_score=doc.original_score,
            )
            for doc, score in scored[:top_k]
        ]


# ===========================================================================
# LLM 评分：Pairwise（两两比较）
# ===========================================================================

class LLMPairwiseReranker(BaseReranker):
    """基于 LLM 的两两比较重排序。

    通过锦标赛式比较获取全局排序。
    调用次数约 O(N log N)，排序更准但更慢。
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.deepseek.com/v1",
        model: str = "deepseek-chat",
        max_concurrency: int = 5,
    ):
        from openai import AsyncOpenAI
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        self._model = model
        self._semaphore = asyncio.Semaphore(max_concurrency)

    @property
    def model_name(self) -> str:
        return self._model

    async def rerank(
        self,
        query: str,
        documents: list[RerankInput],
        top_k: int = 5,
    ) -> list[RerankResult]:
        if not documents:
            return []
        if len(documents) == 1:
            return [RerankResult(
                chunk_id=documents[0].chunk_id,
                content=documents[0].content,
                metadata=documents[0].metadata,
                score=1.0,
                original_score=documents[0].original_score,
            )]

        # 锦标赛排序
        win_count: dict[str, int] = {doc.chunk_id: 0 for doc in documents}

        # 生成所有配对
        pairs = []
        for i in range(len(documents)):
            for j in range(i + 1, len(documents)):
                pairs.append((documents[i], documents[j]))

        async def _compare(doc_a: RerankInput, doc_b: RerankInput) -> str:
            async with self._semaphore:
                prompt = f"""请比较以下两个文档，哪个与查询更相关？

查询：{query}

文档A：{doc_a.content[:1000]}

文档B：{doc_b.content[:1000]}

只输出 A 或 B，表示更相关的那个。"""

                messages = [
                    {"role": "system", "content": "你是一个文档比较助手。只输出 A 或 B。"},
                    {"role": "user", "content": prompt},
                ]

                try:
                    resp = await self._client.chat.completions.create(
                        model=self._model, messages=messages, temperature=0, max_tokens=5,
                    )
                    raw = resp.choices[0].message.content.strip().upper()
                    if "A" in raw and "B" not in raw:
                        return doc_a.chunk_id
                    elif "B" in raw and "A" not in raw:
                        return doc_b.chunk_id
                    else:
                        return doc_a.chunk_id  # 默认
                except Exception:
                    return doc_a.chunk_id

        # 并发比较（限制并发数避免太多请求）
        batch_size = 20
        for i in range(0, len(pairs), batch_size):
            batch = pairs[i:i + batch_size]
            tasks = [_compare(a, b) for a, b in batch]
            winners = await asyncio.gather(*tasks)
            for winner_id in winners:
                win_count[winner_id] += 1

        # 按胜场排序
        doc_map = {doc.chunk_id: doc for doc in documents}
        sorted_ids = sorted(win_count.keys(), key=lambda cid: win_count[cid], reverse=True)

        results: list[RerankResult] = []
        for cid in sorted_ids[:top_k]:
            doc = doc_map[cid]
            score = win_count[cid] / max(1, len(documents) - 1)  # 归一化到 0~1
            results.append(RerankResult(
                chunk_id=doc.chunk_id,
                content=doc.content,
                metadata=doc.metadata,
                score=score,
                original_score=doc.original_score,
            ))

        return results


# ===========================================================================
# Provider 注册表 & 工厂
# ===========================================================================

_PROVIDER_REGISTRY: dict[str, type[BaseReranker]] = {
    "bge-reranker":    BgeReranker,
    "cohere":          CohereReranker,
    "llm-pointwise":   LLMPointwiseReranker,
    "llm-pairwise":    LLMPairwiseReranker,
}


def create_reranker(provider: str, config: dict) -> BaseReranker:
    """工厂函数：根据 provider 创建重排序器。

    参数:
        provider: bge-reranker / cohere / llm-pointwise / llm-pairwise / deepseek / openai / zhipu / qwen / mimo
        config:   provider 配置
    """
    # LLM provider 别名 → llm-pointwise
    llm_aliases = {"deepseek", "openai", "zhipu", "qwen", "mimo"}
    if provider in llm_aliases:
        provider = "llm-pointwise"

    cls = _PROVIDER_REGISTRY.get(provider)
    if cls is None:
        raise ValueError(f"不支持的 Reranker: {provider}，可选: {list(_PROVIDER_REGISTRY.keys())}")

    if provider == "bge-reranker":
        return cls(
            model_name=config.get("model", "BAAI/bge-reranker-v2-m3"),
            device=config.get("device", "cpu"),
            max_workers=config.get("max_workers", 2),
        )
    elif provider == "cohere":
        return cls(
            api_key=config["api_key"],
            model=config.get("model", "rerank-multilingual-v3.0"),
        )
    else:
        # LLM-based rerankers
        url_map = {
            "deepseek": "https://api.deepseek.com/v1",
            "openai": "https://api.openai.com/v1",
            "zhipu": "https://open.bigmodel.cn/api/paas/v4",
            "qwen": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "mimo": "https://api.xiaomi.com/v1",
        }
        llm_provider = config.get("llm_provider", "deepseek")
        base_url = config.get("base_url") or url_map.get(llm_provider, "")
        return cls(
            api_key=config.get("api_key", ""),
            base_url=base_url,
            model=config.get("model", "deepseek-chat"),
            max_concurrency=config.get("max_concurrency", 5),
        )
