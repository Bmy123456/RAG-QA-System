"""
知识库管理 API：知识库 CRUD + 文档上传/列表/删除/状态查询。

所有接口需要登录。
普通用户只能操作自己的知识库 + 读公共知识库。
管理员可操作所有知识库。
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.config.settings import (
    EMBEDDING_CONFIG, EMBEDDING_CACHE_CONFIG, VECTOR_STORE_CONFIG,
    RAW_DIR, MAX_UPLOAD_SIZE_MB, ALLOW_PUBLIC_KB,
)
from backend.db.crud import (
    create_kb, list_kbs, get_kb, update_kb, delete_kb,
    create_document, list_documents, get_document, update_document_status,
    delete_document, count_documents,
)
from backend.db.session import get_db
from backend.api.auth import require_user, require_admin
from backend.models.user import User

router = APIRouter(prefix="/api/kb", tags=["knowledge-base"])


# ---------------------------------------------------------------------------
# 请求/响应模型
# ---------------------------------------------------------------------------

class KBCreateRequest(BaseModel):
    name: str
    description: str = ""
    is_public: bool = False


class KBUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    is_public: bool | None = None


class BatchDocRequest(BaseModel):
    doc_ids: list[int]


class KBResponse(BaseModel):
    id: int
    name: str
    description: str
    is_public: bool = False
    user_id: int | None = None
    doc_count: int = 0
    created_at: str | None = None
    updated_at: str | None = None


class DocumentResponse(BaseModel):
    id: int
    kb_id: int
    filename: str
    file_type: str
    file_size: int
    status: str
    error_msg: str
    chunk_count: int
    progress: int = 0
    progress_msg: str = ""
    created_at: str | None = None


class ChunkResponse(BaseModel):
    chunk_id: str
    text: str
    metadata: dict


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

def _check_kb_owner(kb, user: User):
    """校验知识库所有权：自己是 owner 或管理员。"""
    if kb.user_id is not None and kb.user_id != user.id and user.role != "admin":
        raise HTTPException(status_code=403, detail="无权操作此知识库")


def _kb_to_response(kb, db: Session) -> KBResponse:
    doc_count = count_documents(db, kb_id=kb.id)
    return KBResponse(
        id=kb.id, name=kb.name, description=kb.description,
        is_public=kb.is_public, user_id=kb.user_id,
        doc_count=doc_count,
        created_at=kb.created_at.isoformat() if kb.created_at else None,
        updated_at=kb.updated_at.isoformat() if kb.updated_at else None,
    )


# ---------------------------------------------------------------------------
# 知识库 CRUD
# ---------------------------------------------------------------------------

@router.post("", response_model=KBResponse)
def create_knowledge_base(
    data: KBCreateRequest,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """创建知识库（归当前用户所有）。"""
    kb = create_kb(db, data.name, data.description, user_id=user.id, is_public=data.is_public)
    return _kb_to_response(kb, db)


@router.get("", response_model=list[KBResponse])
def list_knowledge_bases(
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """列出知识库：自己的 + 公共的（管理员看全部）。"""
    if user.role == "admin":
        kbs = list_kbs(db, user_id=None)
    else:
        kbs = list_kbs(db, user_id=user.id, include_public=ALLOW_PUBLIC_KB)
    return [_kb_to_response(kb, db) for kb in kbs]


@router.get("/{kb_id}", response_model=KBResponse)
def get_knowledge_base(
    kb_id: int,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """获取知识库详情（需是自己的或公共的，管理员任意）。"""
    kb = get_kb(db, kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="知识库不存在")
    # 公共知识库或自己的或管理员
    if not kb.is_public and kb.user_id != user.id and user.role != "admin":
        raise HTTPException(status_code=403, detail="无权访问此知识库")
    return _kb_to_response(kb, db)


@router.put("/{kb_id}", response_model=KBResponse)
def update_knowledge_base(
    kb_id: int,
    data: KBUpdateRequest,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """更新知识库（需是 owner 或管理员）。"""
    kb = get_kb(db, kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="知识库不存在")
    _check_kb_owner(kb, user)

    kb = update_kb(db, kb_id, data.name, data.description)
    if data.is_public is not None:
        kb.is_public = data.is_public
        db.commit()
        db.refresh(kb)
    return _kb_to_response(kb, db)


@router.delete("/{kb_id}")
def delete_knowledge_base(
    kb_id: int,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """删除知识库（需是 owner 或管理员）。"""
    kb = get_kb(db, kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="知识库不存在")
    _check_kb_owner(kb, user)

    # 先删除向量库中的数据
    try:
        from backend.core.vector_store import create_vector_store, SearchFilter
        import asyncio
        vs = create_vector_store(VECTOR_STORE_CONFIG["provider"], VECTOR_STORE_CONFIG)
        asyncio.get_event_loop().run_until_complete(
            vs.delete(SearchFilter(kb_id=kb_id))
        )
    except Exception:
        pass

    delete_kb(db, kb_id)
    return {"ok": True}


# ---------------------------------------------------------------------------
# 文档管理
# ---------------------------------------------------------------------------

@router.post("/{kb_id}/upload", response_model=DocumentResponse)
async def upload_document(
    kb_id: int,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """上传文档到知识库（需是 owner 或管理员）。"""
    kb = get_kb(db, kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="知识库不存在")
    _check_kb_owner(kb, user)

    # 读取文件并检查大小
    content = await file.read()
    if len(content) > MAX_UPLOAD_SIZE_MB * 1024 * 1024:
        raise HTTPException(
            status_code=413,
            detail=f"文件大小超过限制（最大 {MAX_UPLOAD_SIZE_MB}MB）",
        )

    # 保存文件
    kb_dir = RAW_DIR / str(kb_id)
    kb_dir.mkdir(parents=True, exist_ok=True)
    file_path = kb_dir / file.filename

    with open(file_path, "wb") as f:
        f.write(content)

    # 检测文件类型
    suffix = Path(file.filename).suffix.lower().lstrip(".")
    file_type_map = {
        "pdf": "pdf", "docx": "docx", "doc": "docx",
        "xlsx": "xlsx", "xls": "xlsx",
        "pptx": "pptx", "ppt": "pptx",
        "txt": "txt", "md": "md",
        "html": "html", "htm": "html",
        "eml": "eml",
        "png": "image", "jpg": "image", "jpeg": "image",
        "bmp": "image", "tiff": "image", "tif": "image",
    }
    file_type = file_type_map.get(suffix, suffix)

    doc = create_document(
        db, kb_id=kb_id,
        filename=file.filename,
        file_type=file_type,
        file_size=len(content),
        file_path=str(file_path),
    )

    background_tasks.add_task(
        _process_document_background,
        doc_id=doc.id,
        file_path=str(file_path),
        kb_id=kb_id,
    )

    return DocumentResponse(
        id=doc.id, kb_id=doc.kb_id, filename=doc.filename,
        file_type=doc.file_type, file_size=doc.file_size,
        status=doc.status, error_msg=doc.error_msg or "",
        chunk_count=doc.chunk_count, progress=doc.progress, progress_msg=doc.progress_msg or "",
        created_at=doc.created_at.isoformat() if doc.created_at else None,
    )


@router.get("/{kb_id}/documents", response_model=list[DocumentResponse])
def list_kb_documents(
    kb_id: int,
    status: str | None = None,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """列出知识库下的文档（需能访问该知识库）。"""
    kb = get_kb(db, kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="知识库不存在")
    if not kb.is_public and kb.user_id != user.id and user.role != "admin":
        raise HTTPException(status_code=403, detail="无权访问此知识库")

    docs = list_documents(db, kb_id, status)
    return [
        DocumentResponse(
            id=d.id, kb_id=d.kb_id, filename=d.filename,
            file_type=d.file_type, file_size=d.file_size,
            status=d.status, error_msg=d.error_msg or "",
            chunk_count=d.chunk_count, progress=d.progress, progress_msg=d.progress_msg or "",
            created_at=d.created_at.isoformat() if d.created_at else None,
        )
        for d in docs
    ]


@router.get("/documents/{doc_id}/status")
def get_document_status(
    doc_id: int,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """查询文档处理状态。"""
    doc = get_document(db, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")
    return {
        "id": doc.id,
        "status": doc.status,
        "error_msg": doc.error_msg or "",
        "chunk_count": doc.chunk_count,
        "progress": doc.progress,
        "progress_msg": doc.progress_msg or "",
    }


@router.post("/documents/{doc_id}/retry")
def retry_document(
    doc_id: int,
    background_tasks: BackgroundTasks,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """重新处理失败或已完成的文档（需是 KB owner 或管理员）。"""
    doc = get_document(db, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")

    kb = get_kb(db, doc.kb_id)
    if kb:
        _check_kb_owner(kb, user)

    if not doc.file_path or not Path(doc.file_path).exists():
        raise HTTPException(status_code=400, detail="原始文件不存在，无法重传")

    # 清除旧向量（避免重复）
    try:
        from backend.core.vector_store import create_vector_store, SearchFilter
        import asyncio
        vs = create_vector_store(VECTOR_STORE_CONFIG["provider"], VECTOR_STORE_CONFIG)
        asyncio.get_event_loop().run_until_complete(
            vs.delete(SearchFilter(filename=doc.filename))
        )
    except Exception:
        pass

    # 重置状态
    update_document_status(db, doc_id, "pending", error_msg="", chunk_count=0, progress=0, progress_msg="")

    # 重新触发后台处理
    background_tasks.add_task(
        _process_document_background,
        doc_id=doc.id,
        file_path=doc.file_path,
        kb_id=doc.kb_id,
    )

    return {"ok": True, "message": "已重新提交处理"}


@router.delete("/documents/{doc_id}")
def delete_kb_document(
    doc_id: int,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """删除文档及对应向量（需是 KB owner 或管理员）。"""
    doc = get_document(db, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")

    # 校验 KB 所有权
    kb = get_kb(db, doc.kb_id)
    if kb:
        _check_kb_owner(kb, user)

    try:
        from backend.core.vector_store import create_vector_store, SearchFilter
        import asyncio
        vs = create_vector_store(VECTOR_STORE_CONFIG["provider"], VECTOR_STORE_CONFIG)
        asyncio.get_event_loop().run_until_complete(
            vs.delete(SearchFilter(filename=doc.filename))
        )
    except Exception:
        pass

    if doc.file_path and Path(doc.file_path).exists():
        Path(doc.file_path).unlink(missing_ok=True)

    delete_document(db, doc_id)
    return {"ok": True}


@router.post("/{kb_id}/documents/batch/delete")
def batch_delete_documents(
    kb_id: int,
    data: BatchDocRequest,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """批量删除文档及对应向量。"""
    kb = get_kb(db, kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="知识库不存在")
    _check_kb_owner(kb, user)

    deleted, failed = [], []
    for doc_id in data.doc_ids:
        doc = get_document(db, doc_id)
        if not doc or doc.kb_id != kb_id:
            failed.append(doc_id)
            continue
        try:
            from backend.core.vector_store import create_vector_store, SearchFilter
            import asyncio
            vs = create_vector_store(VECTOR_STORE_CONFIG["provider"], VECTOR_STORE_CONFIG)
            asyncio.get_event_loop().run_until_complete(
                vs.delete(SearchFilter(filename=doc.filename))
            )
        except Exception:
            pass
        if doc.file_path and Path(doc.file_path).exists():
            Path(doc.file_path).unlink(missing_ok=True)
        delete_document(db, doc_id)
        deleted.append(doc_id)

    return {"ok": True, "deleted": deleted, "failed": failed}


@router.post("/{kb_id}/documents/batch/retry")
def batch_retry_documents(
    kb_id: int,
    data: BatchDocRequest,
    background_tasks: BackgroundTasks,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """批量重传文档。"""
    kb = get_kb(db, kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="知识库不存在")
    _check_kb_owner(kb, user)

    retried, failed = [], []
    for doc_id in data.doc_ids:
        doc = get_document(db, doc_id)
        if not doc or doc.kb_id != kb_id:
            failed.append(doc_id)
            continue
        if not doc.file_path or not Path(doc.file_path).exists():
            failed.append(doc_id)
            continue
        try:
            from backend.core.vector_store import create_vector_store, SearchFilter
            import asyncio
            vs = create_vector_store(VECTOR_STORE_CONFIG["provider"], VECTOR_STORE_CONFIG)
            asyncio.get_event_loop().run_until_complete(
                vs.delete(SearchFilter(filename=doc.filename))
            )
        except Exception:
            pass
        update_document_status(db, doc_id, "pending", error_msg="", chunk_count=0, progress=0, progress_msg="")
        background_tasks.add_task(
            _process_document_background,
            doc_id=doc.id,
            file_path=doc.file_path,
            kb_id=doc.kb_id,
        )
        retried.append(doc_id)

    return {"ok": True, "retried": retried, "failed": failed}


@router.get("/documents/{doc_id}/chunks", response_model=list[ChunkResponse])
def get_document_chunks(
    doc_id: int,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """查看文档的文本块。"""
    doc = get_document(db, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")

    try:
        from backend.core.vector_store import create_vector_store, SearchFilter
        import asyncio
        vs = create_vector_store(VECTOR_STORE_CONFIG["provider"], VECTOR_STORE_CONFIG)
        results = asyncio.get_event_loop().run_until_complete(
            vs.get_by_ids([f"{doc.filename}_chunk_{i}" for i in range(doc.chunk_count)])
        )
        if not results:
            results = asyncio.get_event_loop().run_until_complete(
                vs.search(
                    query_embedding=[0.0] * 768,
                    top_k=doc.chunk_count,
                    search_filter=SearchFilter(filename=doc.filename),
                )
            )
        return [
            ChunkResponse(
                chunk_id=r.chunk_id,
                text=r.text,
                metadata=r.metadata,
            )
            for r in results
        ]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# 后台异步处理
# ---------------------------------------------------------------------------

async def _process_document_background(doc_id: int, file_path: str, kb_id: int):
    """后台处理文档：解析 → 分块 → 向量化 → 入库。"""
    from backend.db.session import SessionLocal
    from backend.core.ingestion import ingest_file
    from backend.core.embedding import EmbeddingService
    from backend.core.vector_store import create_vector_store

    def _on_progress(progress: int, msg: str):
        update_document_status(db, doc_id, "processing", progress=progress, progress_msg=msg)

    db = SessionLocal()
    try:
        update_document_status(db, doc_id, "processing", progress=0, progress_msg="开始处理…")

        chunks = ingest_file(
            file_path=file_path,
            chunk_strategy="hierarchical",
            chunk_size=512,
            chunk_overlap=64,
            parent_chunk_size=2048,
            on_progress=_on_progress,
        )

        if not chunks:
            update_document_status(db, doc_id, "completed", chunk_count=0,
                                   progress=100, progress_msg="处理完成（无文本内容）")
            return

        embedding_service = EmbeddingService(
            provider=EMBEDDING_CONFIG["provider"],
            config=EMBEDDING_CONFIG,
            cache_config=EMBEDDING_CACHE_CONFIG,
        )

        texts = [c.text for c in chunks]
        emb_result = await embedding_service.embed(texts)

        for chunk in chunks:
            if not hasattr(chunk.metadata, "kb_id"):
                chunk.metadata.kb_id = kb_id

        update_document_status(db, doc_id, "processing", progress=80, progress_msg="向量化完成，正在写入数据库…")

        vs = create_vector_store(VECTOR_STORE_CONFIG["provider"], VECTOR_STORE_CONFIG)
        await vs.add_chunks(chunks, emb_result.embeddings)

        update_document_status(db, doc_id, "completed", chunk_count=len(chunks),
                               progress=100, progress_msg="处理完成")

    except Exception as e:
        error_msg = f"{type(e).__name__}: {str(e)}"
        update_document_status(db, doc_id, "failed", error_msg=error_msg)
    finally:
        db.close()
