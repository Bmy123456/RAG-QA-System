"""
检索策略模块：实现稠密检索、稀疏检索（BM25）、混合检索（RRF 融合）、查询扩展。

流程：查询 → 查询扩展 → 稠密检索 + 稀疏检索 → RRF 融合 → 返回 Top-K
"""

from __future__ import annotations

import json
import pickle
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from backend.core.vector_store import BaseVectorStore, SearchFilter, SearchResult

# ---------------------------------------------------------------------------
# 数据类
# ---------------------------------------------------------------------------


@dataclass
class RetrievalResult:
    """统一检索结果格式"""
    chunk_id: str
    content: str                # 文本内容
    metadata: dict              # 元数据
    score: float                # 最终融合分数
    source: str = "dense"       # 来源: dense / sparse / hybrid


# ===========================================================================
# 分词
# ===========================================================================

# 中文字符检测
_CHINESE_PATTERN = re.compile(r"[一-鿿]")


def _tokenize(text: str) -> list[str]:
    """自动检测语言并分词。

    - 纯中文: jieba 分词
    - 纯英文: lower() + split()
    - 混合: jieba 分词（jieba 也能处理英文单词）
    """
    if not text:
        return []

    has_chinese = bool(_CHINESE_PATTERN.search(text))

    if has_chinese:
        import jieba
        tokens = list(jieba.cut(text))
        # 去除纯空白 token
        return [t.strip().lower() for t in tokens if t.strip()]
    else:
        # 纯英文：按空格和标点分割
        tokens = re.findall(r"[a-zA-Z0-9]+", text.lower())
        return tokens


# ===========================================================================
# BM25 索引
# ===========================================================================

class BM25Index:
    """BM25 稀疏检索索引，支持中英文分词、持久化。"""

    def __init__(self, persist_path: str | None = None, k1: float = 1.5, b: float = 0.75,
                 db_session_factory=None):
        self._persist_path = persist_path
        self._db_session_factory = db_session_factory
        self._k1 = k1
        self._b = b

        # 索引数据
        self._chunk_ids: list[str] = []          # chunk_id 列表
        self._chunk_texts: list[str] = []        # 原始文本
        self._chunk_metadatas: list[dict] = []   # 元数据
        self._tokenized_corpus: list[list[str]] = []  # 分词后的语料
        self._bm25 = None                        # rank_bm25.BM25Okapi 实例

    def build(self, chunks: list[tuple[str, str, dict]]) -> None:
        """从 chunk 列表构建 BM25 索引。

        参数:
            chunks: [(chunk_id, text, metadata), ...]
        """
        from rank_bm25 import BM25Okapi

        self._chunk_ids = [c[0] for c in chunks]
        self._chunk_texts = [c[1] for c in chunks]
        self._chunk_metadatas = [c[2] for c in chunks]
        self._tokenized_corpus = [_tokenize(text) for text in self._chunk_texts]

        if self._tokenized_corpus:
            self._bm25 = BM25Okapi(self._tokenized_corpus, k1=self._k1, b=self._b)
        else:
            self._bm25 = None

    def search(self, query: str, top_k: int = 20) -> list[tuple[str, float, dict]]:
        """BM25 检索。

        返回:
            [(chunk_id, score, metadata), ...]，按 score 降序
        """
        if self._bm25 is None or not self._chunk_ids:
            return []

        tokens = _tokenize(query)
        if not tokens:
            return []

        scores = self._bm25.get_scores(tokens)

        # 取 top_k
        indexed_scores = list(enumerate(scores))
        indexed_scores.sort(key=lambda x: x[1], reverse=True)

        results = []
        for idx, score in indexed_scores[:top_k]:
            if score > 0:
                results.append((
                    self._chunk_ids[idx],
                    float(score),
                    self._chunk_metadatas[idx],
                ))

        return results

    def add_chunks(self, chunks: list[tuple[str, str, dict]]) -> None:
        """增量添加（重新构建整个索引）。"""
        # 合并到现有数据
        existing = list(zip(self._chunk_ids, self._chunk_texts, self._chunk_metadatas))
        all_chunks = existing + chunks
        self.build(all_chunks)

    def remove_by_ids(self, chunk_ids: set[str]) -> None:
        """按 chunk_id 移除并重建索引。"""
        remaining = [
            (cid, text, meta)
            for cid, text, meta in zip(self._chunk_ids, self._chunk_texts, self._chunk_metadatas)
            if cid not in chunk_ids
        ]
        self.build(remaining)

    def _serialize(self) -> bytes:
        """序列化索引数据为 bytes。"""
        data = {
            "chunk_ids": self._chunk_ids,
            "chunk_texts": self._chunk_texts,
            "chunk_metadatas": self._chunk_metadatas,
            "k1": self._k1,
            "b": self._b,
        }
        return pickle.dumps(data)

    def _deserialize(self, raw: bytes) -> bool:
        """从 bytes 反序列化并重建索引。"""
        data = pickle.loads(raw)
        self._k1 = data.get("k1", self._k1)
        self._b = data.get("b", self._b)
        chunks = list(zip(data["chunk_ids"], data["chunk_texts"], data["chunk_metadatas"]))
        self.build(chunks)
        return True

    def save(self) -> None:
        """持久化到 SQLite 或磁盘文件。"""
        blob = self._serialize()

        # 优先写 SQLite
        if self._db_session_factory:
            from backend.models.bm25 import BM25Persist
            from datetime import datetime
            db = self._db_session_factory()
            try:
                row = db.query(BM25Persist).first()
                if row:
                    row.data = blob
                    row.updated_at = datetime.utcnow()
                else:
                    db.add(BM25Persist(id=1, data=blob))
                db.commit()
            finally:
                db.close()
            return

        # 回退到 pickle 文件
        if self._persist_path:
            path = Path(self._persist_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "wb") as f:
                f.write(blob)

    def load(self) -> bool:
        """从 SQLite 或磁盘文件加载。"""
        # 优先读 SQLite
        if self._db_session_factory:
            from backend.models.bm25 import BM25Persist
            db = self._db_session_factory()
            try:
                row = db.query(BM25Persist).first()
                if row and row.data:
                    return self._deserialize(row.data)
            finally:
                db.close()

        # 回退到 pickle 文件
        if self._persist_path:
            path = Path(self._persist_path)
            if path.exists():
                try:
                    with open(path, "rb") as f:
                        return self._deserialize(f.read())
                except Exception:
                    return False
        return False

    @property
    def size(self) -> int:
        return len(self._chunk_ids)


# ===========================================================================
# 查询扩展
# ===========================================================================

class QueryExpander:
    """查询扩展：同义词表扩展 + LLM HyDE（生成假设文档）。"""

    def __init__(
        self,
        synonym_path: str | None = None,
        llm_provider: str = "deepseek",
        llm_config: dict | None = None,
    ):
        self._synonyms: dict[str, list[str]] = {}
        self._llm_provider = llm_provider
        self._llm_config = llm_config or {}
        self._llm = None  # 延迟初始化

        if synonym_path:
            self._load_synonyms(synonym_path)

    def _load_synonyms(self, path: str):
        """加载同义词表（JSON 格式）"""
        p = Path(path)
        if p.exists():
            with open(p, "r", encoding="utf-8") as f:
                self._synonyms = json.load(f)

    async def expand_synonyms(self, query: str) -> list[str]:
        """同义词扩展：返回扩展后的查询列表（含原始查询）。

        遍历同义词表，如果查询中包含某个关键词，则生成包含同义词的扩展查询。
        """
        expanded = [query]

        for keyword, synonyms in self._synonyms.items():
            if keyword in query:
                for syn in synonyms:
                    expanded_query = query.replace(keyword, syn)
                    if expanded_query not in expanded:
                        expanded.append(expanded_query)

        return expanded

    async def expand_hyde(self, query: str) -> str:
        """HyDE：让 LLM 生成假设性回答文档。

        用生成的假文档做检索，往往比原始查询效果更好。
        """
        llm = self._get_llm()

        prompt = f"""请根据以下问题，写一段可能包含答案的文档内容（200字左右）。
要求：内容要像真实文档一样自然，包含相关的专业术语和具体信息。

问题：{query}"""

        messages = [
            {"role": "system", "content": "你是一个知识丰富的文档撰写助手。"},
            {"role": "user", "content": prompt},
        ]

        result = ""
        async for chunk in llm.chat_stream(messages):
            result += chunk

        return result.strip()

    async def expand(self, query: str, method: str = "all") -> list[str]:
        """统一入口：返回扩展查询列表。

        参数:
            query:  原始查询
            method: "synonym" / "hyde" / "all"

        返回:
            扩展后的查询列表（含原始查询）
        """
        queries = [query]

        if method in ("synonym", "all"):
            syn_queries = await self.expand_synonyms(query)
            queries.extend([q for q in syn_queries if q != query])

        if method in ("hyde", "all"):
            try:
                hyde_doc = await self.expand_hyde(query)
                if hyde_doc:
                    queries.append(hyde_doc)
            except Exception:
                pass  # HyDE 失败不影响主流程

        return queries

    def _get_llm(self):
        if self._llm is None:
            from backend.core.embedding import _PROVIDER_REGISTRY as EMB_REGISTRY
            # 复用 embedding 模块的 provider 注册表思路，直接用 LLM 的
            # 这里延迟导入避免循环
            from backend.config.settings import LLM_CONFIG
            cfg = {**LLM_CONFIG, **self._llm_config}

            provider = self._llm_provider or cfg.get("provider", "deepseek")
            self._llm = self._create_llm(provider, cfg)
        return self._llm

    @staticmethod
    def _create_llm(provider: str, config: dict):
        from openai import AsyncOpenAI

        url_map = {
            "deepseek": "https://api.deepseek.com/v1",
            "openai": "https://api.openai.com/v1",
            "zhipu": "https://open.bigmodel.cn/api/paas/v4",
            "qwen": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "mimo": "https://api.xiaomi.com/v1",
        }

        base_url = config.get("base_url") or url_map.get(provider, "")
        api_key = config.get("api_key", "")
        model = config.get("model", "deepseek-chat")

        client = AsyncOpenAI(api_key=api_key, base_url=base_url)

        class _LLMWrapper:
            async def chat_stream(self, messages):
                resp = await client.chat.completions.create(
                    model=model, messages=messages, stream=True,
                    temperature=config.get("temperature", 0.3),
                )
                async for chunk in resp:
                    delta = chunk.choices[0].delta
                    if delta.content:
                        yield delta.content

        return _LLMWrapper()


# ===========================================================================
# 混合检索器
# ===========================================================================

class HybridRetriever:
    """混合检索器：稠密检索 + 稀疏检索（BM25）+ RRF 融合 + 查询扩展。"""

    def __init__(
        self,
        vector_store: BaseVectorStore,
        embedding_service: Any,  # EmbeddingService（避免循环导入用 Any）
        config: dict | None = None,
    ):
        cfg = config or {}
        self._vector_store = vector_store
        self._embedding_service = embedding_service

        self._dense_weight = cfg.get("dense_weight", 1.0)
        self._sparse_weight = cfg.get("sparse_weight", 1.0)
        self._rrf_k = cfg.get("rrf_k", 60)
        self._initial_top_k = cfg.get("initial_top_k", 20)
        self._final_top_k = cfg.get("final_top_k", 5)

        # BM25 索引
        bm25_path = cfg.get("bm25_persist_path")
        db_factory = cfg.get("bm25_db_session_factory")
        self._bm25 = BM25Index(persist_path=bm25_path, db_session_factory=db_factory)

        # 查询扩展
        qe_cfg = cfg.get("query_expansion", {})
        self._expander = QueryExpander(
            synonym_path=qe_cfg.get("synonym_path"),
            llm_provider=qe_cfg.get("llm_provider", "deepseek"),
            llm_config=qe_cfg.get("llm_config"),
        )
        self._expand_enabled = qe_cfg.get("enabled", True)
        self._expand_method = qe_cfg.get("method", "all")

        # 尝试加载已有 BM25 索引
        self._bm25.load()

    # -- 公开方法 -----------------------------------------------------------

    async def retrieve(
        self,
        query: str,
        search_filter: SearchFilter | None = None,
        top_k: int | None = None,
        strategy: str = "hybrid",
    ) -> list[RetrievalResult]:
        """统一检索入口。

        参数:
            query:         用户查询
            search_filter: 元数据过滤
            top_k:         返回结果数（默认用配置值）
            strategy:      "dense" / "sparse" / "hybrid"

        返回:
            list[RetrievalResult]，按 score 降序
        """
        top_k = top_k or self._final_top_k

        # 查询扩展
        if self._expand_enabled and strategy in ("dense", "hybrid"):
            queries = await self._expander.expand(query, method=self._expand_method)
        else:
            queries = [query]

        # 稠密检索
        dense_results: list[RetrievalResult] = []
        if strategy in ("dense", "hybrid"):
            dense_results = await self._multi_query_dense(queries, search_filter)

        # 稀疏检索
        sparse_results: list[RetrievalResult] = []
        if strategy in ("sparse", "hybrid"):
            sparse_results = self._sparse_search(query, search_filter)

        # 融合
        if strategy == "dense":
            results = dense_results
        elif strategy == "sparse":
            results = sparse_results
        else:
            results = self._rrf_fuse(dense_results, sparse_results, self._rrf_k)

        # 去重 + 截断
        results = self._deduplicate(results)
        return results[:top_k]

    def index_chunks(self, chunks: list[Any]) -> None:
        """构建/更新 BM25 索引。

        参数:
            chunks: Chunk 对象列表（来自 ingestion 模块）
        """
        bm25_data = [
            (c.chunk_id, c.text, self._chunk_meta_to_dict(c.metadata))
            for c in chunks
        ]
        self._bm25.add_chunks(bm25_data)
        self._bm25.save()

    def remove_from_index(self, chunk_ids: list[str]) -> None:
        """从 BM25 索引中移除指定 chunk"""
        self._bm25.remove_by_ids(set(chunk_ids))
        self._bm25.save()

    def save_index(self) -> None:
        """手动保存 BM25 索引"""
        self._bm25.save()

    def load_index(self) -> bool:
        """手动加载 BM25 索引"""
        return self._bm25.load()

    @property
    def bm25_size(self) -> int:
        return self._bm25.size

    # -- 稠密检索 -----------------------------------------------------------

    async def _dense_search(
        self,
        query: str,
        query_embedding: list[float],
        search_filter: SearchFilter | None,
        top_k: int,
    ) -> list[RetrievalResult]:
        """单次稠密检索"""
        results = await self._vector_store.search(
            query_embedding=query_embedding,
            top_k=top_k,
            search_filter=search_filter,
        )
        return [
            RetrievalResult(
                chunk_id=r.chunk_id,
                content=r.text,
                metadata=r.metadata,
                score=r.score,
                source="dense",
            )
            for r in results
        ]

    async def _multi_query_dense(
        self,
        queries: list[str],
        search_filter: SearchFilter | None,
    ) -> list[RetrievalResult]:
        """多查询稠密检索（查询扩展后合并）"""
        all_results: list[RetrievalResult] = []

        for q in queries:
            try:
                emb = await self._embedding_service.embed_query(q)
                results = await self._dense_search(q, emb, search_filter, self._initial_top_k)
                all_results.extend(results)
            except Exception:
                continue

        return all_results

    # -- 稀疏检索 -----------------------------------------------------------

    def _sparse_search(
        self,
        query: str,
        search_filter: SearchFilter | None,
    ) -> list[RetrievalResult]:
        """BM25 稀疏检索"""
        bm25_results = self._bm25.search(query, top_k=self._initial_top_k)

        results: list[RetrievalResult] = []
        for chunk_id, score, meta in bm25_results:
            # 应用过滤
            if search_filter and not self._match_filter(meta, search_filter):
                continue
            results.append(RetrievalResult(
                chunk_id=chunk_id,
                content="",  # BM25 不存储原文，需要后续填充
                metadata=meta,
                score=score,
                source="sparse",
            ))

        return results

    # -- RRF 融合 -----------------------------------------------------------

    def _rrf_fuse(
        self,
        dense_results: list[RetrievalResult],
        sparse_results: list[RetrievalResult],
        k: int = 60,
    ) -> list[RetrievalResult]:
        """RRF (Reciprocal Rank Fusion) 融合。

        score = dense_weight * Σ 1/(k + rank_dense) + sparse_weight * Σ 1/(k + rank_sparse)

        同一 chunk_id 出现在两个列表中时，分数叠加。
        """
        score_map: dict[str, float] = {}
        result_map: dict[str, RetrievalResult] = {}

        # 稠密结果按 rank 计分
        for rank, r in enumerate(dense_results):
            rrf_score = self._dense_weight / (k + rank + 1)
            if r.chunk_id in score_map:
                score_map[r.chunk_id] += rrf_score
            else:
                score_map[r.chunk_id] = rrf_score
                result_map[r.chunk_id] = r

        # 稀疏结果按 rank 计分
        for rank, r in enumerate(sparse_results):
            rrf_score = self._sparse_weight / (k + rank + 1)
            if r.chunk_id in score_map:
                score_map[r.chunk_id] += rrf_score
            else:
                score_map[r.chunk_id] = rrf_score
                result_map[r.chunk_id] = r

        # 更新分数并排序
        results: list[RetrievalResult] = []
        for cid, score in score_map.items():
            r = result_map[cid]
            results.append(RetrievalResult(
                chunk_id=r.chunk_id,
                content=r.content,
                metadata=r.metadata,
                score=score,
                source="hybrid",
            ))

        results.sort(key=lambda x: x.score, reverse=True)
        return results

    # -- 工具 ---------------------------------------------------------------

    @staticmethod
    def _deduplicate(results: list[RetrievalResult]) -> list[RetrievalResult]:
        """按 chunk_id 去重，保留分数最高的"""
        seen: dict[str, RetrievalResult] = {}
        for r in results:
            if r.chunk_id not in seen or r.score > seen[r.chunk_id].score:
                seen[r.chunk_id] = r
        deduped = list(seen.values())
        deduped.sort(key=lambda x: x.score, reverse=True)
        return deduped

    @staticmethod
    def _match_filter(meta: dict, search_filter: SearchFilter) -> bool:
        """检查元数据是否匹配过滤条件"""
        if search_filter.kb_id is not None and meta.get("kb_id") != search_filter.kb_id:
            return False
        if search_filter.file_type is not None and meta.get("file_type") != search_filter.file_type:
            return False
        if search_filter.filename is not None and meta.get("filename") != search_filter.filename:
            return False
        if search_filter.chunk_level is not None and meta.get("chunk_level") != search_filter.chunk_level:
            return False
        return True

    @staticmethod
    def _chunk_meta_to_dict(meta) -> dict:
        if hasattr(meta, "__dataclass_fields__"):
            return {k: v for k, v in meta.__dict__.items() if v is not None}
        return dict(meta) if isinstance(meta, dict) else {}
