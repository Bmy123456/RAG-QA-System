from pathlib import Path
from sqlalchemy.orm import Session
from app.models import Document
from app.document.loader import parse_document, get_file_type
from app.rag.splitter import split_document
from app.rag.embedding import embed_chunks
from app.storage.file_store import save_file, delete_file
from app.storage.vector_store import add_chunks


async def process_document_async(doc_id: int, file_path: str, file_type: str, db_url: str):
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        doc = db.query(Document).filter(Document.id == doc_id).first()
        if not doc:
            return

        try:
            pages = parse_document(file_path, file_type)
            all_chunks = []
            for page_data in pages:
                meta = {"filename": doc.filename, "file_type": file_type, "page": page_data.get("page")}
                meta.update(page_data.get("metadata", {}))
                chunks = split_document(page_data["text"], meta)
                all_chunks.extend(chunks)

            if not all_chunks:
                raise ValueError("No text extracted from document")

            embeddings = await embed_chunks(all_chunks)
            add_chunks(doc.kb_id, all_chunks, embeddings)

            doc.status = "completed"
            doc.chunk_count = len(all_chunks)

        except Exception as e:
            doc.status = "failed"
            doc.error_msg = str(e)[:500]

        db.commit()
    finally:
        db.close()


def upload_document(db: Session, kb_id: int, user_id: int, filename: str, file_bytes: bytes) -> Document:
    ext = Path(filename).suffix.lower().lstrip(".")
    file_type = get_file_type(ext)
    if file_type is None:
        raise ValueError(f"Unsupported file type: {ext}")

    max_size = 50 * 1024 * 1024
    if len(file_bytes) > max_size:
        raise ValueError(f"File too large: {len(file_bytes)} bytes (max {max_size})")

    stored_path, _ = save_file(file_bytes, filename, user_id)
    doc = Document(
        kb_id=kb_id, user_id=user_id, filename=filename,
        file_type=file_type, file_size=len(file_bytes),
        file_path=stored_path, status="processing",
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


def list_documents(db: Session, kb_id: int, user_id: int) -> list[Document]:
    return db.query(Document).filter(
        Document.kb_id == kb_id, Document.user_id == user_id
    ).order_by(Document.created_at.desc()).all()


def get_document(db: Session, doc_id: int, user_id: int) -> Document | None:
    return db.query(Document).filter(
        Document.id == doc_id, Document.user_id == user_id
    ).first()


def delete_document(db: Session, doc_id: int, user_id: int) -> bool:
    doc = get_document(db, doc_id, user_id)
    if not doc:
        return False
    delete_file(doc.file_path)
    db.delete(doc)
    db.commit()
    return True
