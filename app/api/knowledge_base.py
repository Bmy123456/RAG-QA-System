from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.database import get_db
from app.middleware.auth import get_current_user
from app.models import User
from app.services import kb_service

router = APIRouter(prefix="/api/kb", tags=["knowledge_base"])


class KBCreate(BaseModel):
    name: str
    description: str = ""


class KBResponse(BaseModel):
    id: int
    name: str
    description: str
    created_at: str

    model_config = {"from_attributes": True}


@router.post("", response_model=KBResponse)
def create_kb(data: KBCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    kb = kb_service.create_kb(db, user.id, data.name, data.description)
    return KBResponse(id=kb.id, name=kb.name, description=kb.description, created_at=str(kb.created_at))


@router.get("", response_model=list[KBResponse])
def list_kb(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    kbs = kb_service.list_kbs(db, user.id)
    return [KBResponse(id=k.id, name=k.name, description=k.description, created_at=str(k.created_at)) for k in kbs]


@router.delete("/{kb_id}")
def delete_kb(kb_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    ok = kb_service.delete_kb(db, kb_id, user.id)
    if not ok:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    return {"ok": True}
