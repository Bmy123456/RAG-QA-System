from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, BackgroundTasks
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.database import get_db
from app.middleware.auth import get_current_user
from app.models import User
from app.services import document_service, kb_service
from app.config import get_config

router = APIRouter(prefix="/api/documents", tags=["documents"])


class DocumentResponse(BaseModel):
    id: int
    filename: str
    file_type: str
    file_size: int
    status: str
    error_msg: str
    chunk_count: int
    created_at: str

    model_config = {"from_attributes": True}


@router.post("/upload/{kb_id}", response_model=DocumentResponse)
async def upload_doc(
    kb_id: int,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    kb = kb_service.get_kb(db, kb_id, user.id)
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    try:
        content = await file.read()
        doc = document_service.upload_document(db, kb_id, user.id, file.filename, content)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    config = get_config()
    db_url = config["database"]["url"]
    background_tasks.add_task(document_service.process_document_async, doc.id, doc.file_path, doc.file_type, db_url)

    return DocumentResponse(
        id=doc.id, filename=doc.filename, file_type=doc.file_type,
        file_size=doc.file_size, status=doc.status, error_msg=doc.error_msg or "",
        chunk_count=doc.chunk_count, created_at=str(doc.created_at),
    )


@router.get("/{kb_id}", response_model=list[DocumentResponse])
def list_docs(kb_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    kb = kb_service.get_kb(db, kb_id, user.id)
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    docs = document_service.list_documents(db, kb_id, user.id)
    return [DocumentResponse(
        id=d.id, filename=d.filename, file_type=d.file_type,
        file_size=d.file_size, status=d.status, error_msg=d.error_msg or "",
        chunk_count=d.chunk_count, created_at=str(d.created_at),
    ) for d in docs]


@router.get("/detail/{doc_id}", response_model=DocumentResponse)
def get_doc(doc_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    doc = document_service.get_document(db, doc_id, user.id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return DocumentResponse(
        id=doc.id, filename=doc.filename, file_type=doc.file_type,
        file_size=doc.file_size, status=doc.status, error_msg=doc.error_msg or "",
        chunk_count=doc.chunk_count, created_at=str(doc.created_at),
    )


@router.delete("/{doc_id}")
def delete_doc(doc_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    ok = document_service.delete_document(db, doc_id, user.id)
    if not ok:
        raise HTTPException(status_code=404, detail="Document not found")
    return {"ok": True}
