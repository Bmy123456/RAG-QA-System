"""
管理员 API：向量库监控。

所有接口需要 admin 角色。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.config.settings import VECTOR_STORE_CONFIG
from backend.db.session import get_db
from backend.db.crud import get_kb
from backend.api.auth import require_admin
from backend.models.user import User

router = APIRouter(prefix="/api/admin/vectors", tags=["admin-vectors"])


def _get_vs():
    from backend.core.vector_store import create_vector_store
    return create_vector_store(VECTOR_STORE_CONFIG["provider"], VECTOR_STORE_CONFIG)


# ---------------------------------------------------------------------------
# 概览统计
# ---------------------------------------------------------------------------

@router.get("/stats")
async def vector_stats(
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """向量库总览：collection 数量、总 chunk 数、各 collection 摘要。"""
    vs = _get_vs()
    client = vs._get_client()

    collections_info = []
    total_chunks = 0

    for coll_info in client.list_collections():
        name = coll_info.name if hasattr(coll_info, "name") else str(coll_info)
        try:
            coll = client.get_collection(name)
            count = coll.count()
        except Exception:
            count = 0

        # 从 collection 名解析 kb_id
        kb_id = None
        if name.startswith(vs._prefix):
            try:
                kb_id = int(name[len(vs._prefix):])
            except ValueError:
                pass

        kb_name = None
        if kb_id:
            kb = get_kb(db, kb_id)
            kb_name = kb.name if kb else "(已删除)"

        collections_info.append({
            "collection": name,
            "kb_id": kb_id,
            "kb_name": kb_name,
            "chunk_count": count,
        })
        total_chunks += count

    return {
        "total_collections": len(collections_info),
        "total_chunks": total_chunks,
        "collections": collections_info,
    }


# ---------------------------------------------------------------------------
# 分页查询某个 collection 的 chunks
# ---------------------------------------------------------------------------

@router.get("/{kb_id}/chunks")
async def list_vector_chunks(
    kb_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    filename: str | None = None,
    chunk_level: str | None = None,
    user: User = Depends(require_admin),
):
    """分页列出某个知识库向量库中的 chunks。"""
    vs = _get_vs()
    client = vs._get_client()
    coll_name = vs._get_collection_name(kb_id)

    try:
        collection = client.get_collection(coll_name)
    except Exception:
        raise HTTPException(status_code=404, detail=f"Collection {coll_name} 不存在")

    # 构建过滤条件
    from backend.core.vector_store import SearchFilter
    search_filter = SearchFilter(
        kb_id=kb_id,
        filename=filename,
        chunk_level=chunk_level,
    )
    where = vs._build_where_clause(search_filter) if not search_filter.is_empty() else None

    total = collection.count(where=where) if where else collection.count()
    offset = (page - 1) * page_size

    if offset >= total and total > 0:
        raise HTTPException(status_code=400, detail="页码超出范围")

    result = collection.get(
        where=where,
        offset=offset,
        limit=page_size,
        include=["documents", "metadatas"],
    )

    items = []
    if result and result["ids"]:
        for i, cid in enumerate(result["ids"]):
            meta = result["metadatas"][i] if result["metadatas"] else {}
            doc = result["documents"][i] if result["documents"] else ""
            items.append({
                "chunk_id": cid,
                "text": doc,
                "text_preview": doc[:200] + ("…" if len(doc) > 200 else ""),
                "metadata": meta,
                "filename": meta.get("filename", ""),
                "chunk_level": meta.get("chunk_level", ""),
                "modality": meta.get("modality", "text"),
                "created_at": meta.get("created_at", ""),
            })

    return {
        "kb_id": kb_id,
        "collection": coll_name,
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": items,
    }


# ---------------------------------------------------------------------------
# 单个 chunk 详情
# ---------------------------------------------------------------------------

@router.get("/{kb_id}/chunks/{chunk_id:path}")
async def get_vector_chunk(
    kb_id: int,
    chunk_id: str,
    user: User = Depends(require_admin),
):
    """获取单个 chunk 的完整内容和元数据。"""
    vs = _get_vs()
    client = vs._get_client()
    coll_name = vs._get_collection_name(kb_id)

    try:
        collection = client.get_collection(coll_name)
    except Exception:
        raise HTTPException(status_code=404, detail=f"Collection {coll_name} 不存在")

    result = collection.get(
        ids=[chunk_id],
        include=["documents", "metadatas", "embeddings"],
    )

    if not result or not result["ids"]:
        raise HTTPException(status_code=404, detail=f"Chunk {chunk_id} 不存在")

    meta = result["metadatas"][0] if result["metadatas"] else {}
    doc = result["documents"][0] if result["documents"] else ""
    emb = result["embeddings"][0] if result["embeddings"] else None

    return {
        "chunk_id": result["ids"][0],
        "text": doc,
        "text_length": len(doc),
        "metadata": meta,
        "embedding_dim": len(emb) if emb else 0,
        "embedding_preview": emb[:10] if emb else None,
    }


# ---------------------------------------------------------------------------
# 搜索 chunks（关键词 / 元数据）
# ---------------------------------------------------------------------------

@router.get("/{kb_id}/search")
async def search_vector_chunks(
    kb_id: int,
    q: str = Query("", description="文本关键词（空则返回全部）"),
    filename: str | None = None,
    chunk_level: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: User = Depends(require_admin),
):
    """在指定知识库的向量库中按关键词搜索 chunks。"""
    vs = _get_vs()
    client = vs._get_client()
    coll_name = vs._get_collection_name(kb_id)

    try:
        collection = client.get_collection(coll_name)
    except Exception:
        raise HTTPException(status_code=404, detail=f"Collection {coll_name} 不存在")

    # 构建 where 过滤
    from backend.core.vector_store import SearchFilter
    search_filter = SearchFilter(kb_id=kb_id, filename=filename, chunk_level=chunk_level)
    where = vs._build_where_clause(search_filter) if not search_filter.is_empty() else None

    # ChromaDB 支持 $contains 文本搜索（需 chromadb >= 0.4）
    if q:
        try:
            text_filter = {"$contains": q}
            if where:
                where = {"$and": [where, {"text": text_filter}]}
            else:
                where = {"text": text_filter}
        except Exception:
            pass

    total = collection.count(where=where) if where else collection.count()
    offset = (page - 1) * page_size

    try:
        result = collection.get(
            where=where,
            offset=offset,
            limit=page_size,
            include=["documents", "metadatas"],
        )
    except Exception:
        # $contains 不支持时回退全量获取后过滤
        result = collection.get(include=["documents", "metadatas"])
        if result and result["ids"] and q:
            filtered_ids, filtered_docs, filtered_metas = [], [], []
            for i, doc in enumerate(result["documents"] or []):
                if q.lower() in doc.lower():
                    filtered_ids.append(result["ids"][i])
                    filtered_docs.append(doc)
                    filtered_metas.append(result["metadatas"][i] if result["metadatas"] else {})
            total = len(filtered_ids)
            start = offset
            end = offset + page_size
            result = {
                "ids": filtered_ids[start:end],
                "documents": filtered_docs[start:end],
                "metadatas": filtered_metas[start:end],
            }

    items = []
    if result and result["ids"]:
        for i, cid in enumerate(result["ids"]):
            meta = result["metadatas"][i] if result["metadatas"] else {}
            doc = result["documents"][i] if result["documents"] else ""
            items.append({
                "chunk_id": cid,
                "text_preview": doc[:200] + ("…" if len(doc) > 200 else ""),
                "metadata": meta,
                "filename": meta.get("filename", ""),
            })

    return {
        "kb_id": kb_id,
        "query": q,
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": items,
    }
