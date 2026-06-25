"""
Embedding 向量化模块：统一接口封装多种 Embedding 服务。

支持：
- 云端 API：OpenAI / DeepSeek / 智谱 / Qwen（兼容 OpenAI 协议）
- 本地模型：sentence-transformers / bge-large

特性：
- 批量向量化 + 并行加速（asyncio 信号量 / 多线程自动切换）
- 向量归一化（余弦相似度场景）
- 内存 + SQLite 磁盘双层缓存
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import sqlite3
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# 数据类
# ---------------------------------------------------------------------------

@dataclass
class EmbeddingResult:
    """向量化结果"""
    embeddings: list[list[float]]   # 向量列表
    dimensions: int                 # 单个向量维度
    model: str                      # 模型名
    token_count: int                # 总 token 数（如 API 返回）


# ===========================================================================
# 缓存层
# ===========================================================================

class EmbeddingCache:
    """双层缓存：内存 dict + SQLite 磁盘。"""

    def __init__(self, config: dict | None = None):
        cfg = config or {}
        self._enabled = cfg.get("enabled", True)
        self._backend = cfg.get("backend", "both")  # memory / disk / both
        self._memory: dict[str, list[float]] = {}
        self._disk_conn: sqlite3.Connection | None = None

        if self._enabled and self._backend in ("disk", "both"):
            from backend.config.settings import DATA_DIR
            db_path = cfg.get("db_path", str(DATA_DIR / "embedding_cache.db"))
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
            self._disk_conn = sqlite3.connect(db_path, check_same_thread=False)
            self._disk_conn.execute(
                "CREATE TABLE IF NOT EXISTS cache "
                "(hash TEXT PRIMARY KEY, embedding TEXT, dimensions INTEGER, model TEXT)"
            )
            self._disk_conn.commit()

    # -- 单条 ---------------------------------------------------------------

    def get(self, text: str, model: str = "") -> list[float] | None:
        h = self._hash(text, model)
        # 内存
        if self._backend in ("memory", "both") and h in self._memory:
            return self._memory[h]
        # 磁盘
        if self._disk_conn:
            row = self._disk_conn.execute(
                "SELECT embedding FROM cache WHERE hash=?", (h,)
            ).fetchone()
            if row:
                emb = json.loads(row[0])
                self._memory[h] = emb  # 回填内存
                return emb
        return None

    def put(self, text: str, embedding: list[float], model: str = ""):
        h = self._hash(text, model)
        if self._backend in ("memory", "both"):
            self._memory[h] = embedding
        if self._disk_conn:
            self._disk_conn.execute(
                "INSERT OR REPLACE INTO cache (hash, embedding, dimensions, model) VALUES (?,?,?,?)",
                (h, json.dumps(embedding), len(embedding), model),
            )
            self._disk_conn.commit()

    # -- 批量 ---------------------------------------------------------------

    def get_batch(self, texts: list[str], model: str = "") -> tuple[list[int], list[list[float]]]:
        """返回 (已缓存的原始索引列表, 对应向量列表)"""
        cached_indices: list[int] = []
        cached_embeddings: list[list[float]] = []
        for i, t in enumerate(texts):
            emb = self.get(t, model)
            if emb is not None:
                cached_indices.append(i)
                cached_embeddings.append(emb)
        return cached_indices, cached_embeddings

    def put_batch(self, texts: list[str], embeddings: list[list[float]], model: str = ""):
        for t, e in zip(texts, embeddings):
            self.put(t, e, model)

    # -- 工具 ---------------------------------------------------------------

    @staticmethod
    def _hash(text: str, model: str) -> str:
        return hashlib.md5(f"{model}::{text}".encode()).hexdigest()


# ===========================================================================
# Provider 基类
# ===========================================================================

class BaseEmbeddingProvider(ABC):
    """Embedding 提供者抽象基类。"""

    @abstractmethod
    async def embed(self, texts: list[str]) -> EmbeddingResult:
        """批量向量化"""
        ...

    @property
    @abstractmethod
    def dimensions(self) -> int:
        """向量维度"""
        ...

    @property
    def is_local(self) -> bool:
        """是否为本地模型（影响并行策略）"""
        return False

    @property
    @abstractmethod
    def model_name(self) -> str:
        """模型标识"""
        ...


# ===========================================================================
# 云端 Provider（统一用 OpenAI 兼容协议）
# ===========================================================================

class _OpenAICompatibleEmbedding(BaseEmbeddingProvider):
    """OpenAI 兼容 Embedding 的公共基类。"""

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        dimensions: int,
        batch_size: int = 32,
        max_concurrency: int = 10,
    ):
        from openai import AsyncOpenAI
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        self._model = model
        self._dimensions = dimensions
        self._batch_size = batch_size
        self._semaphore = asyncio.Semaphore(max_concurrency)

    @property
    def dimensions(self) -> int:
        return self._dimensions

    @property
    def model_name(self) -> str:
        return self._model

    async def embed(self, texts: list[str]) -> EmbeddingResult:
        if not texts:
            return EmbeddingResult(embeddings=[], dimensions=self._dimensions, model=self._model, token_count=0)

        # 分批
        batches = [texts[i:i + self._batch_size] for i in range(0, len(texts), self._batch_size)]

        all_embeddings: list[list[float]] = []
        total_tokens = 0

        async def _embed_batch(batch: list[str]) -> tuple[list[list[float]], int]:
            async with self._semaphore:
                resp = await self._client.embeddings.create(model=self._model, input=batch)
                embs = [d.embedding for d in resp.data]
                tokens = getattr(resp, "usage", None)
                tc = tokens.total_tokens if tokens else 0
                return embs, tc

        tasks = [_embed_batch(b) for b in batches]
        results = await asyncio.gather(*tasks)

        for embs, tc in results:
            all_embeddings.extend(embs)
            total_tokens += tc

        return EmbeddingResult(
            embeddings=all_embeddings,
            dimensions=self._dimensions,
            model=self._model,
            token_count=total_tokens,
        )


class OpenAIEmbedding(_OpenAICompatibleEmbedding):
    """OpenAI Embedding (text-embedding-ada-002 / text-embedding-3-small)"""

    def __init__(self, api_key: str, base_url: str = "https://api.openai.com/v1",
                 model: str = "text-embedding-3-small", dimensions: int = 1536,
                 batch_size: int = 32, max_concurrency: int = 10):
        super().__init__(api_key, base_url, model, dimensions, batch_size, max_concurrency)


class DeepSeekEmbedding(_OpenAICompatibleEmbedding):
    """DeepSeek Embedding"""

    def __init__(self, api_key: str, base_url: str = "https://api.deepseek.com/v1",
                 model: str = "deepseek-embed", dimensions: int = 4096,
                 batch_size: int = 32, max_concurrency: int = 10):
        super().__init__(api_key, base_url, model, dimensions, batch_size, max_concurrency)


class ZhipuEmbedding(_OpenAICompatibleEmbedding):
    """智谱 Embedding"""

    def __init__(self, api_key: str, base_url: str = "https://open.bigmodel.cn/api/paas/v4",
                 model: str = "embedding-3", dimensions: int = 2048,
                 batch_size: int = 32, max_concurrency: int = 10):
        super().__init__(api_key, base_url, model, dimensions, batch_size, max_concurrency)


class QwenEmbedding(_OpenAICompatibleEmbedding):
    """通义千问 Embedding"""

    def __init__(self, api_key: str, base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1",
                 model: str = "text-embedding-v3", dimensions: int = 1024,
                 batch_size: int = 32, max_concurrency: int = 10):
        super().__init__(api_key, base_url, model, dimensions, batch_size, max_concurrency)


class MiMoEmbedding(_OpenAICompatibleEmbedding):
    """小米 MiMo Embedding"""

    def __init__(self, api_key: str, base_url: str = "https://api.xiaomi.com/v1",
                 model: str = "mimo-embed", dimensions: int = 2048,
                 batch_size: int = 32, max_concurrency: int = 10):
        super().__init__(api_key, base_url, model, dimensions, batch_size, max_concurrency)


# ===========================================================================
# 本地 Provider
# ===========================================================================

class SentenceTransformerEmbedding(BaseEmbeddingProvider):
    """本地 sentence-transformers / bge-large 模型。

    使用 ThreadPoolExecutor 做多线程推理，避免阻塞事件循环。
    """

    def __init__(
        self,
        model_name: str = "BAAI/bge-large-zh-v1.5",
        device: str = "cpu",
        max_workers: int = 4,
    ):
        self._model_name = model_name
        self._device = device
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._model = None  # 延迟加载
        self._dimensions: int | None = None

    def _load_model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self._model_name, device=self._device)
            self._dimensions = self._model.get_sentence_embedding_dimension()

    @property
    def dimensions(self) -> int:
        self._load_model()
        return self._dimensions

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def is_local(self) -> bool:
        return True

    async def embed(self, texts: list[str]) -> EmbeddingResult:
        if not texts:
            return EmbeddingResult(embeddings=[], dimensions=self.dimensions, model=self._model_name, token_count=0)

        loop = asyncio.get_event_loop()
        embeddings = await loop.run_in_executor(self._executor, self._sync_embed, texts)

        return EmbeddingResult(
            embeddings=embeddings,
            dimensions=self.dimensions,
            model=self._model_name,
            token_count=0,  # 本地模型不返回 token 数
        )

    def _sync_embed(self, texts: list[str]) -> list[list[float]]:
        self._load_model()
        vecs = self._model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
        return vecs.tolist()


# ===========================================================================
# Provider 注册表
# ===========================================================================

_PROVIDER_REGISTRY: dict[str, type[BaseEmbeddingProvider]] = {
    "openai":              OpenAIEmbedding,
    "deepseek":            DeepSeekEmbedding,
    "zhipu":               ZhipuEmbedding,
    "qwen":                QwenEmbedding,
    "mimo":                MiMoEmbedding,
    "sentence-transformers": SentenceTransformerEmbedding,
    "bge-large":           SentenceTransformerEmbedding,
}


# ===========================================================================
# 主服务
# ===========================================================================

class EmbeddingService:
    """Embedding 主服务：编排 provider + 缓存 + 归一化。"""

    def __init__(self, provider: str, config: dict, cache_config: dict | None = None):
        """
        参数:
            provider:     提供者名（openai / deepseek / zhipu / qwen / sentence-transformers / bge-large）
            config:       provider 配置（api_key, base_url, model, dimensions, batch_size, ...）
            cache_config: 缓存配置（enabled, backend, db_path）
        """
        self._provider_name = provider
        self._provider = self._create_provider(provider, config)
        self._cache = EmbeddingCache(cache_config)
        self._normalize = config.get("normalize", True)

    # -- 公开方法 -----------------------------------------------------------

    async def embed(self, texts: list[str], use_cache: bool = True) -> EmbeddingResult:
        """批量向量化（带缓存）。

        参数:
            texts:     待向量化的文本列表
            use_cache: 是否使用缓存

        返回:
            EmbeddingResult
        """
        if not texts:
            return EmbeddingResult(embeddings=[], dimensions=self._provider.dimensions,
                                   model=self._provider.model_name, token_count=0)

        model = self._provider.model_name
        embeddings_map: dict[int, list[float]] = {}
        uncached_indices: list[int] = []
        uncached_texts: list[str] = []

        # 1. 查缓存
        if use_cache:
            cached_indices, cached_embs = self._cache.get_batch(texts, model)
            for idx, emb in zip(cached_indices, cached_embs):
                embeddings_map[idx] = emb
            for i in range(len(texts)):
                if i not in embeddings_map:
                    uncached_indices.append(i)
                    uncached_texts.append(texts[i])
        else:
            uncached_indices = list(range(len(texts)))
            uncached_texts = texts

        # 2. 调用 provider
        if uncached_texts:
            result = await self._provider.embed(uncached_texts)
            new_embs = result.embeddings

            # 归一化
            if self._normalize:
                new_embs = [_normalize_vector(e) for e in new_embs]

            # 写入缓存
            if use_cache:
                self._cache.put_batch(uncached_texts, new_embs, model)

            # 合并到结果 map
            for idx, emb in zip(uncached_indices, new_embs):
                embeddings_map[idx] = emb
        else:
            result = None

        # 3. 按原始顺序组装
        ordered_embeddings = [embeddings_map[i] for i in range(len(texts))]

        return EmbeddingResult(
            embeddings=ordered_embeddings,
            dimensions=self._provider.dimensions,
            model=model,
            token_count=result.token_count if result else 0,
        )

    async def embed_query(self, query: str, use_cache: bool = True) -> list[float]:
        """单条查询向量化。"""
        result = await self.embed([query], use_cache=use_cache)
        return result.embeddings[0]

    @property
    def dimensions(self) -> int:
        return self._provider.dimensions

    @property
    def model_name(self) -> str:
        return self._provider.model_name

    # -- 内部 ---------------------------------------------------------------

    @staticmethod
    def _create_provider(provider: str, config: dict) -> BaseEmbeddingProvider:
        cls = _PROVIDER_REGISTRY.get(provider)
        if cls is None:
            raise ValueError(f"不支持的 Embedding 提供者: {provider}，可选: {list(_PROVIDER_REGISTRY.keys())}")

        if provider in ("sentence-transformers", "bge-large"):
            model_name = config.get("model", "BAAI/bge-large-zh-v1.5")
            device = config.get("device", "cpu")
            max_workers = config.get("max_workers", 4)
            return cls(model_name=model_name, device=device, max_workers=max_workers)
        else:
            return cls(
                api_key=config["api_key"],
                base_url=config.get("base_url", ""),
                model=config.get("model", ""),
                dimensions=config.get("dimensions", 1536),
                batch_size=config.get("batch_size", 32),
                max_concurrency=config.get("max_concurrency", 10),
            )


# ===========================================================================
# 工具函数
# ===========================================================================

def _normalize_vector(vec: list[float]) -> list[float]:
    """L2 归一化"""
    norm = math.sqrt(sum(x * x for x in vec))
    if norm == 0:
        return vec
    return [x / norm for x in vec]
