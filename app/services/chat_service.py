from typing import AsyncIterator
from sqlalchemy.orm import Session
from app.models import Conversation, Message
from app.rag.retriever import retrieve_with_rerank
from app.rag.generator import build_prompt, generate_answer
from app.llm.deepseek import DeepSeekLLM


def create_conversation(db: Session, user_id: int, kb_id: int, title: str = "New Chat") -> Conversation:
    conv = Conversation(user_id=user_id, kb_id=kb_id, title=title)
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return conv


def list_conversations(db: Session, user_id: int, kb_id: int | None = None) -> list[Conversation]:
    q = db.query(Conversation).filter(Conversation.user_id == user_id)
    if kb_id is not None:
        q = q.filter(Conversation.kb_id == kb_id)
    return q.order_by(Conversation.created_at.desc()).all()


def get_conversation(db: Session, conv_id: int, user_id: int) -> Conversation | None:
    return db.query(Conversation).filter(
        Conversation.id == conv_id, Conversation.user_id == user_id
    ).first()


def get_history(db: Session, conv_id: int, limit: int = 10) -> list[dict]:
    messages = (
        db.query(Message)
        .filter(Message.conversation_id == conv_id)
        .order_by(Message.created_at.desc())
        .limit(limit)
        .all()
    )
    messages.reverse()
    return [{"role": m.role, "content": m.content} for m in messages]


def save_message(db: Session, conv_id: int, role: str, content: str, sources: list[dict] | None = None):
    msg = Message(conversation_id=conv_id, role=role, content=content, sources=sources)
    db.add(msg)
    db.commit()
    conv = db.query(Conversation).filter(Conversation.id == conv_id).first()
    if conv and role == "user" and conv.title == "New Chat":
        conv.title = content[:50]
        db.commit()


async def chat_stream(
    db: Session, user_id: int, kb_id: int, conv_id: int, question: str,
) -> AsyncIterator[str]:
    save_message(db, conv_id, "user", question)

    llm = DeepSeekLLM()
    query_embeddings = await llm.embed([question])
    chunks = await retrieve_with_rerank(kb_id, question, query_embeddings[0])

    sources = []
    for i, chunk in enumerate(chunks, 1):
        sources.append({
            "index": i,
            "filename": chunk["metadata"].get("filename", "unknown"),
            "page": chunk["metadata"].get("page"),
            "snippet": chunk["text"][:200],
        })

    history = get_history(db, conv_id)
    messages = build_prompt(question, chunks, history[:-1])

    full_answer = ""
    async for token in generate_answer(messages):
        full_answer += token
        yield token

    save_message(db, conv_id, "assistant", full_answer, sources)
