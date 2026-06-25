"""
向量数据库模块：管理向量存储、索引、增删查。

支持：
- ChromaDB（完整实现，轻量开发）
- Milvus / Qdrant / Weaviate（预留接口）

特性：
- 本地持久化 + client/server 远程模式
- 集合组织可配置（per-kb collection 或 单 collection + metadata filter）
- 元数据过滤（知识库ID、文档类型、时间范围等）
- 多模态向量预留（图片 Embedding）
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from backend.core.ingestion import Chunk


# ---------------------------------------------------------------------------
# 数据类
# ---------------------------------------------------------------------------

@dataclass
class SearchFilter:
    """元数据过滤条件。

    所有字段均为可选，多个字段之间是 AND 关系。
    """
    kb_id: int | None = None            # 知识库 ID
    file_type: str | None = None        # 文件类型 (pdf/docx/xlsx/...)
    filename: str | None = None         # 文件名（支持前缀匹配）
    chunk_level: str | None = None      # parent / child
    modality: str | None = None         # text / image（多模态预留）
    created_after: str | None = None    # 时间下限 (ISO 格式)
    created_before: str | None = None   # 时间上限 (ISO 格式)
    chunk_ids: list[str] | None = None  # 指定 chunk_id 列表

    def is_empty(self) -> bool:
        return all(v is None for v in self.__dict__.values())


@dataclass
class SearchResult:
    """检索结果"""
    chunk_id: str
    text: str
    score: float                        # 相似度分数 (0~1)
    metadata: dict                      # 完整元数据
    modality: str = "text"              # text / image（多模态预留）


# ---------------------------------------------------------------------------
# 抽象基类
# ---------------------------------------------------------------------------

class BaseVectorStore(ABC):
    """向量数据库统一接口。"""

    @abstractmethod
    async def add_chunks(
        self,
        chunks: list[Chunk],
        embeddings: list[list[float]],
        modality: str = "text",
    ) -> None:
        """添加 chunks 及其向量到存储。

        参数:
            chunks:     Chunk 对象列表（来自 ingestion 模块）
            embeddings: 对应的向量列表，与 chunks 一一对应
            modality:   向量模态 "text" / "image"（多模态预留）
        """
        ...

    @abstractmethod
    async def search(
        self,
        query_embedding: list[float],
        top_k: int = 10,
        search_filter: SearchFilter | None = None,
        collection_hint: str | None = None,
    ) -> list[SearchResult]:
        """向量检索。

        参数:
            query_embedding:  查询向量
            top_k:            返回结果数
            search_filter:    元数据过滤条件
            collection_hint:  指定 collection 名（per-kb 模式下可直接指定）

        返回:
            list[SearchResult]，按相似度降序
        """
        ...

    @abstractmethod
    async def delete(self, delete_filter: SearchFilter) -> int:
        """按条件删除向量。

        返回:
            删除的数量
        """
        ...

    @abstractmethod
    async def count(self, search_filter: SearchFilter | None = None) -> int:
        """统计数量。"""
        ...

    @abstractmethod
    async def get_by_ids(self, chunk_ids: list[str]) -> list[SearchResult]:
        """按 chunk_id 精确获取。"""
        ...


# ===========================================================================
# ChromaDB 实现
# ===========================================================================

class ChromaVectorStore(BaseVectorStore):
    """ChromaDB 向量存储。

    支持两种连接模式：
    - 本地持久化: chromadb.PersistentClient(path=...)
    - 远程服务:   chromadb.HttpClient(host=..., port=...)

    支持两种集合组织模式：
    - per-kb: 每个知识库一个 collection（名为 prefix + kb_id），检索快、隔离好
    - single: 所有数据存一个 collection，通过 metadata filter 区分，管理简单
    """

    def __init__(self, config: dict):
        self._config = config
        self._persist_directory = config.get("persist_directory", "data/chroma_db")
        self._collection_mode = config.get("collection_mode", "per-kb")
        self._prefix = config.get("collection_prefix", "kb_")
        self._default_collection_name = config.get("default_collection", "all_docs")
        self._client = None

    def _get_client(self):
        if self._client is None:
            host = self._config.get("host")
            port = self._config.get("port")
            if host and port:
                import chromadb
                self._client = chromadb.HttpClient(host=host, port=int(port))
            else:
                import chromadb
                from pathlib import Path
                Path(self._persist_directory).mkdir(parents=True, exist_ok=True)
                self._client = chromadb.PersistentClient(path=self._persist_directory)
        return self._client

    # -- Collection 管理 ----------------------------------------------------

    def _get_collection_name(self, kb_id: int | None = None) -> str:
        if self._collection_mode == "per-kb":
            if kb_id is None:
                raise ValueError("per-kb 模式下必须提供 kb_id")
            return f"{self._prefix}{kb_id}"
        else:
            return self._default_collection_name

    def _get_or_create_collection(self, name: str):
        client = self._get_client()
        return client.get_or_create_collection(
            name=name,
            metadata={"hnsw:space": "cosine"},  # 余弦相似度
        )

    def _get_kb_id_from_chunks(self, chunks: list[Chunk]) -> int | None:
        """从 chunk 的 metadata 中提取 kb_id（如果有）"""
        for c in chunks:
            kb = c.metadata.__dict__.get("kb_id") if hasattr(c.metadata, "kb_id") else None
            if kb is not None:
                return kb
        return None

    # -- 核心操作 -----------------------------------------------------------

    async def add_chunks(
        self,
        chunks: list[Chunk],
        embeddings: list[list[float]],
        modality: str = "text",
    ) -> None:
        if not chunks:
            return

        if len(chunks) != len(embeddings):
            raise ValueError(f"chunks ({len(chunks)}) 与 embeddings ({len(embeddings)}) 数量不匹配")

        # 按 collection 分组
        groups: dict[str, list[tuple[Chunk, list[float]]]] = {}
        if self._collection_mode == "per-kb":
            kb_id = self._get_kb_id_from_chunks(chunks)
            if kb_id is None:
                raise ValueError("per-kb 模式下 chunk metadata 中缺少 kb_id")
            coll_name = self._get_collection_name(kb_id)
            groups[coll_name] = list(zip(chunks, embeddings))
        else:
            coll_name = self._get_collection_name()
            groups[coll_name] = list(zip(chunks, embeddings))

        for coll_name, items in groups.items():
            collection = self._get_or_create_collection(coll_name)

            ids = []
            docs = []
            metadatas = []
            embs = []

            for chunk, emb in items:
                ids.append(chunk.chunk_id)
                docs.append(chunk.text)
                meta = self._chunk_metadata_to_dict(chunk.metadata)
                meta["modality"] = modality
                meta["created_at"] = datetime.utcnow().isoformat()
                metadatas.append(meta)
                embs.append(emb)

            collection.upsert(
                ids=ids,
                embeddings=embs,
                documents=docs,
                metadatas=metadatas,
            )

    async def search(
        self,
        query_embedding: list[float],
        top_k: int = 10,
        search_filter: SearchFilter | None = None,
        collection_hint: str | None = None,
    ) -> list[SearchResult]:
        # 确定要搜索的 collections
        collections_to_search = self._resolve_search_collections(search_filter, collection_hint)

        all_results: list[SearchResult] = []

        for coll_name in collections_to_search:
            try:
                collection = self._get_or_create_collection(coll_name)
            except Exception:
                continue

            where = self._build_where_clause(search_filter) if search_filter else None

            try:
                result = collection.query(
                    query_embeddings=[query_embedding],
                    n_results=top_k,
                    where=where if where else None,
                    include=["documents", "metadatas", "distances"],
                )
            except Exception:
                continue

            if not result or not result["ids"] or not result["ids"][0]:
                continue

            for i, chunk_id in enumerate(result["ids"][0]):
                distance = result["distances"][0][i]
                # ChromaDB cosine distance: 0=完全相同, 2=完全相反
                # 转为相似度分数: score = 1 - distance/2
                score = max(0.0, 1.0 - distance / 2.0)

                meta = result["metadatas"][0][i] if result["metadatas"] else {}
                doc = result["documents"][0][i] if result["documents"] else ""

                all_results.append(SearchResult(
                    chunk_id=chunk_id,
                    text=doc,
                    score=score,
                    metadata=meta,
                    modality=meta.get("modality", "text"),
                ))

        # 按 score 降序排列，取 top_k
        all_results.sort(key=lambda x: x.score, reverse=True)
        return all_results[:top_k]

    async def delete(self, delete_filter: SearchFilter) -> int:
        if delete_filter.is_empty():
            raise ValueError("delete 至少需要一个过滤条件")

        collections = self._resolve_search_collections(delete_filter)
        total_deleted = 0

        for coll_name in collections:
            try:
                collection = self._get_or_create_collection(coll_name)
            except Exception:
                continue

            where = self._build_where_clause(delete_filter)
            if where:
                try:
                    # 先查询匹配的 IDs
                    result = collection.get(where=where, include=[])
                    if result and result["ids"]:
                        collection.delete(ids=result["ids"])
                        total_deleted += len(result["ids"])
                except Exception:
                    continue

        return total_deleted

    async def count(self, search_filter: SearchFilter | None = None) -> int:
        collections = self._resolve_search_collections(search_filter)
        total = 0

        for coll_name in collections:
            try:
                collection = self._get_or_create_collection(coll_name)
                if search_filter and not search_filter.is_empty():
                    where = self._build_where_clause(search_filter)
                    result = collection.get(where=where, include=[])
                    total += len(result["ids"]) if result and result["ids"] else 0
                else:
                    total += collection.count()
            except Exception:
                continue

        return total

    async def get_by_ids(self, chunk_ids: list[str]) -> list[SearchResult]:
        if not chunk_ids:
            return []

        results: list[SearchResult] = []
        client = self._get_client()

        # 遍历所有 collections 查找
        for coll_info in client.list_collections():
            coll_name = coll_info.name if hasattr(coll_info, "name") else str(coll_info)
            try:
                collection = client.get_collection(coll_name)
                result = collection.get(
                    ids=chunk_ids,
                    include=["documents", "metadatas"],
                )
                if result and result["ids"]:
                    for i, cid in enumerate(result["ids"]):
                        meta = result["metadatas"][i] if result["metadatas"] else {}
                        doc = result["documents"][i] if result["documents"] else ""
                        results.append(SearchResult(
                            chunk_id=cid,
                            text=doc,
                            score=1.0,  # 精确匹配
                            metadata=meta,
                            modality=meta.get("modality", "text"),
                        ))
            except Exception:
                continue

        return results

    # -- 内部工具 -----------------------------------------------------------

    def _resolve_search_collections(
        self,
        search_filter: SearchFilter | None,
        collection_hint: str | None = None,
    ) -> list[str]:
        """确定要搜索的 collection 列表"""
        if collection_hint:
            return [collection_hint]

        if self._collection_mode == "per-kb":
            if search_filter and search_filter.kb_id is not None:
                return [self._get_collection_name(search_filter.kb_id)]
            else:
                # 遍历所有 kb_ 前缀的 collection
                return self._list_kb_collections()
        else:
            return [self._get_collection_name()]

    def _list_kb_collections(self) -> list[str]:
        """列出所有 kb_ 前缀的 collection"""
        client = self._get_client()
        names = []
        for coll_info in client.list_collections():
            name = coll_info.name if hasattr(coll_info, "name") else str(coll_info)
            if name.startswith(self._prefix):
                names.append(name)
        return names

    @staticmethod
    def _build_where_clause(search_filter: SearchFilter) -> dict | None:
        """将 SearchFilter 转为 ChromaDB where 条件"""
        conditions: list[dict] = []

        if search_filter.kb_id is not None:
            conditions.append({"kb_id": {"$eq": search_filter.kb_id}})
        if search_filter.file_type is not None:
            conditions.append({"file_type": {"$eq": search_filter.file_type}})
        if search_filter.filename is not None:
            conditions.append({"filename": {"$eq": search_filter.filename}})
        if search_filter.chunk_level is not None:
            conditions.append({"chunk_level": {"$eq": search_filter.chunk_level}})
        if search_filter.modality is not None:
            conditions.append({"modality": {"$eq": search_filter.modality}})

        if not conditions:
            return None
        if len(conditions) == 1:
            return conditions[0]
        return {"$and": conditions}

    @staticmethod
    def _chunk_metadata_to_dict(meta) -> dict:
        """将 ChunkMetadata dataclass 转为 dict（去掉 None 值字段）"""
        if hasattr(meta, "__dataclass_fields__"):
            d = {}
            for k, v in meta.__dict__.items():
                if v is not None:
                    d[k] = v
            return d
        return dict(meta) if isinstance(meta, dict) else {}


# ===========================================================================
# 预留 Provider（仅定义接口，不实现）
# ===========================================================================

class MilvusVectorStore(BaseVectorStore):
    """Milvus 向量存储（预留接口）"""

    def __init__(self, config: dict):
        raise NotImplementedError("MilvusVectorStore 尚未实现，请使用 ChromaVectorStore")

    async def add_chunks(self, chunks, embeddings, modality="text"): ...
    async def search(self, query_embedding, top_k=10, search_filter=None, collection_hint=None): ...
    async def delete(self, delete_filter): ...
    async def count(self, search_filter=None): ...
    async def get_by_ids(self, chunk_ids): ...


class QdrantVectorStore(BaseVectorStore):
    """Qdrant 向量存储（预留接口）"""

    def __init__(self, config: dict):
        raise NotImplementedError("QdrantVectorStore 尚未实现，请使用 ChromaVectorStore")

    async def add_chunks(self, chunks, embeddings, modality="text"): ...
    async def search(self, query_embedding, top_k=10, search_filter=None, collection_hint=None): ...
    async def delete(self, delete_filter): ...
    async def count(self, search_filter=None): ...
    async def get_by_ids(self, chunk_ids): ...


class WeaviateVectorStore(BaseVectorStore):
    """Weaviate 向量存储（预留接口）"""

    def __init__(self, config: dict):
        raise NotImplementedError("WeaviateVectorStore 尚未实现，请使用 ChromaVectorStore")

    async def add_chunks(self, chunks, embeddings, modality="text"): ...
    async def search(self, query_embedding, top_k=10, search_filter=None, collection_hint=None): ...
    async def delete(self, delete_filter): ...
    async def count(self, search_filter=None): ...
    async def get_by_ids(self, chunk_ids): ...


# ===========================================================================
# Provider 注册表 & 工厂
# ===========================================================================

_PROVIDER_REGISTRY: dict[str, type[BaseVectorStore]] = {
    "chroma":    ChromaVectorStore,
    "milvus":    MilvusVectorStore,
    "qdrant":    QdrantVectorStore,
    "weaviate":  WeaviateVectorStore,
}


def create_vector_store(provider: str = "chroma", config: dict | None = None) -> BaseVectorStore:
    """工厂函数：根据 provider 名创建对应的向量存储实例。"""
    cls = _PROVIDER_REGISTRY.get(provider)
    if cls is None:
        raise ValueError(f"不支持的向量数据库: {provider}，可选: {list(_PROVIDER_REGISTRY.keys())}")
    return cls(config or {})
