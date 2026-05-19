import uuid
from langchain_text_splitters import RecursiveCharacterTextSplitter
from app.config import get_config

config = get_config()


def get_splitter() -> RecursiveCharacterTextSplitter:
    return RecursiveCharacterTextSplitter(
        chunk_size=config["document"]["chunk_size"],
        chunk_overlap=config["document"]["chunk_overlap"],
        separators=["\n\n", "\n", "。", ".", "！", "!", "？", "?", " ", ""],
    )


def split_document(text: str, metadata: dict) -> list[dict]:
    splitter = get_splitter()
    chunks = splitter.split_text(text)
    results = []
    for chunk in chunks:
        chunk_id = uuid.uuid4().hex[:16]
        chunk_meta = {**metadata, "chunk_index": len(results)}
        results.append({"id": chunk_id, "text": chunk, "metadata": chunk_meta})
    return results
