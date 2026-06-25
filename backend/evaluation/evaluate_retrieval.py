"""
离线检索评估：Precision@K, Recall@K, MRR, MAP。

输入数据格式：
[
    {
        "query": "什么是RAG？",
        "relevant_doc_ids": ["chunk_id_1", "chunk_id_2"],
        "kb_id": 1
    }
]
"""

from __future__ import annotations

import json
from pathlib import Path


def precision_at_k(retrieved: list[str], relevant: set[str], k: int) -> float:
    """Precision@K：前 K 个结果中相关文档的比例。"""
    top_k = retrieved[:k]
    hits = sum(1 for doc_id in top_k if doc_id in relevant)
    return hits / k if k > 0 else 0.0


def recall_at_k(retrieved: list[str], relevant: set[str], k: int) -> float:
    """Recall@K：前 K 个结果中召回了多少相关文档。"""
    top_k = retrieved[:k]
    hits = sum(1 for doc_id in top_k if doc_id in relevant)
    return hits / len(relevant) if relevant else 0.0


def mrr(retrieved: list[str], relevant: set[str]) -> float:
    """MRR (Mean Reciprocal Rank)：第一个相关文档的排名倒数。"""
    for i, doc_id in enumerate(retrieved):
        if doc_id in relevant:
            return 1.0 / (i + 1)
    return 0.0


def average_precision(retrieved: list[str], relevant: set[str]) -> float:
    """AP (Average Precision)：相关文档排名的平均精度。"""
    if not relevant:
        return 0.0
    hits = 0
    sum_precision = 0.0
    for i, doc_id in enumerate(retrieved):
        if doc_id in relevant:
            hits += 1
            sum_precision += hits / (i + 1)
    return sum_precision / len(relevant)


def evaluate_retrieval(test_data: list[dict], db=None) -> dict:
    """执行检索评估。

    参数:
        test_data: [{"query": "...", "relevant_doc_ids": [...], "kb_id": 1}]
        db:        数据库会话（可选，用于同步调用检索）

    返回:
        {"precision@5": 0.8, "recall@5": 0.6, "mrr": 0.75, "map": 0.7, "num_queries": 10}
    """
    k_values = [1, 3, 5, 10]
    results = {
        "num_queries": len(test_data),
        "queries": [],
    }

    # 初始化指标
    for k in k_values:
        results[f"precision@{k}"] = 0.0
        results[f"recall@{k}"] = 0.0
    results["mrr"] = 0.0
    results["map"] = 0.0

    for item in test_data:
        query = item["query"]
        relevant = set(item.get("relevant_doc_ids", []))
        retrieved = item.get("retrieved_doc_ids", [])

        # 如果没有预计算的 retrieved_ids，需要实际运行检索
        if not retrieved and db:
            retrieved = _run_retrieval(query, item.get("kb_id"))

        query_result = {"query": query, "num_relevant": len(relevant)}

        for k in k_values:
            p = precision_at_k(retrieved, relevant, k)
            r = recall_at_k(retrieved, relevant, k)
            results[f"precision@{k}"] += p
            results[f"recall@{k}"] += r
            query_result[f"precision@{k}"] = round(p, 4)
            query_result[f"recall@{k}"] = round(r, 4)

        query_result["mrr"] = round(mrr(retrieved, relevant), 4)
        query_result["ap"] = round(average_precision(retrieved, relevant), 4)
        results["mrr"] += query_result["mrr"]
        results["map"] += query_result["ap"]

        results["queries"].append(query_result)

    # 取平均
    n = max(1, len(test_data))
    for k in k_values:
        results[f"precision@{k}"] = round(results[f"precision@{k}"] / n, 4)
        results[f"recall@{k}"] = round(results[f"recall@{k}"] / n, 4)
    results["mrr"] = round(results["mrr"] / n, 4)
    results["map"] = round(results["map"] / n, 4)

    return results


def _run_retrieval(query: str, kb_id: int | None = None) -> list[str]:
    """实际运行检索，返回 chunk_id 列表。"""
    try:
        from backend.config.settings import (
            EMBEDDING_CONFIG, EMBEDDING_CACHE_CONFIG,
            VECTOR_STORE_CONFIG, RETRIEVAL_CONFIG,
        )
        from backend.core.embedding import EmbeddingService
        from backend.core.vector_store import create_vector_store, SearchFilter
        from backend.core.retrieval import HybridRetriever
        import asyncio

        emb_service = EmbeddingService(
            provider=EMBEDDING_CONFIG["provider"],
            config=EMBEDDING_CONFIG,
            cache_config=EMBEDDING_CACHE_CONFIG,
        )
        vs = create_vector_store(VECTOR_STORE_CONFIG["provider"], VECTOR_STORE_CONFIG)
        retriever = HybridRetriever(vs, emb_service, RETRIEVAL_CONFIG)

        search_filter = SearchFilter(kb_id=kb_id) if kb_id else None
        loop = asyncio.new_event_loop()
        results = loop.run_until_complete(
            retriever.retrieve(query, search_filter, top_k=20)
        )
        return [r.chunk_id for r in results]
    except Exception:
        return []
