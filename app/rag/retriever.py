from app.storage.vector_store import query as vs_query
from app.llm.deepseek import DeepSeekLLM, DeepSeekReranker
from app.config import get_config

config = get_config()


async def retrieve_with_rerank(kb_id: int, query_text: str, query_embedding: list[float]) -> list[dict]:
    coarse_k = config["retrieval"]["coarse_top_k"]
    rerank_k = config["retrieval"]["rerank_top_k"]
    threshold = config["retrieval"]["similarity_threshold"]

    coarse_results = vs_query(kb_id, query_embedding, top_k=coarse_k, threshold=threshold)

    if len(coarse_results) == 0:
        return []

    if len(coarse_results) <= rerank_k:
        return coarse_results

    llm = DeepSeekLLM()
    reranker = DeepSeekReranker(llm)
    ranked = await reranker.rerank(query_text, [r["text"] for r in coarse_results])

    reranked = [coarse_results[idx] for idx, _ in ranked[:rerank_k]]
    return reranked
