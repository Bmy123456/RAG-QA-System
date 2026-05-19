from sqlalchemy.orm import Session
from app.models import KnowledgeBase
from app.storage.vector_store import delete_collection


def create_kb(db: Session, user_id: int, name: str, description: str = "") -> KnowledgeBase:
    kb = KnowledgeBase(user_id=user_id, name=name, description=description)
    db.add(kb)
    db.commit()
    db.refresh(kb)
    return kb


def list_kbs(db: Session, user_id: int) -> list[KnowledgeBase]:
    return db.query(KnowledgeBase).filter(
        KnowledgeBase.user_id == user_id
    ).order_by(KnowledgeBase.created_at.desc()).all()


def get_kb(db: Session, kb_id: int, user_id: int) -> KnowledgeBase | None:
    return db.query(KnowledgeBase).filter(
        KnowledgeBase.id == kb_id, KnowledgeBase.user_id == user_id
    ).first()


def delete_kb(db: Session, kb_id: int, user_id: int) -> bool:
    kb = get_kb(db, kb_id, user_id)
    if not kb:
        return False
    delete_collection(kb_id)
    db.delete(kb)
    db.commit()
    return True
