from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.database import get_db
from app.middleware.auth import get_current_user
from app.models import User, Message
from app.services import chat_service, kb_service

router = APIRouter(prefix="/api/chat", tags=["chat"])


class ChatRequest(BaseModel):
    kb_id: int
    question: str
    conversation_id: int | None = None


class ConversationResponse(BaseModel):
    id: int
    kb_id: int
    title: str
    created_at: str

    model_config = {"from_attributes": True}


class MessageResponse(BaseModel):
    id: int
    role: str
    content: str
    sources: list[dict] | None
    created_at: str

    model_config = {"from_attributes": True}


@router.post("/stream")
async def chat_stream_endpoint(
    data: ChatRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    kb = kb_service.get_kb(db, data.kb_id, user.id)
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    conv_id = data.conversation_id
    if conv_id is None:
        conv = chat_service.create_conversation(db, user.id, data.kb_id)
        conv_id = conv.id

    conv = chat_service.get_conversation(db, conv_id, user.id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    async def event_stream():
        async for token in chat_service.chat_stream(db, user.id, data.kb_id, conv_id, data.question):
            yield f"data: {token}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/conversations/{kb_id}", response_model=list[ConversationResponse])
def list_conversations(kb_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    convs = chat_service.list_conversations(db, user.id, kb_id)
    return [ConversationResponse(id=c.id, kb_id=c.kb_id, title=c.title, created_at=str(c.created_at)) for c in convs]


@router.get("/messages/{conv_id}", response_model=list[MessageResponse])
def get_messages(conv_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    conv = chat_service.get_conversation(db, conv_id, user.id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    messages = db.query(Message).filter(
        Message.conversation_id == conv_id
    ).order_by(Message.created_at.asc()).all()
    return [MessageResponse(id=m.id, role=m.role, content=m.content, sources=m.sources, created_at=str(m.created_at)) for m in messages]


@router.delete("/conversations/{conv_id}")
def delete_conversation(conv_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    conv = chat_service.get_conversation(db, conv_id, user.id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    db.delete(conv)
    db.commit()
    return {"ok": True}
