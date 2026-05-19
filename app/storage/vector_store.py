import chromadb
from chromadb.config import Settings as ChromaSettings
from app.config import get_config

config = get_config()
CHROMA_DIR = config["vector_store"]["persist_dir"]

_client = chromadb.PersistentClient(path=CHROMA_DIR, settings=ChromaSettings(anonymized_telemetry=False))


def get_collection(kb_id: int):
    return _client.get_or_create_collection(name=f"kb_{kb_id}")


def add_chunks(kb_id: int, chunks: list[dict], embeddings: list[list[float]]):
    collection = get_collection(kb_id)
    ids = [c["id"] for c in chunks]
    documents = [c["text"] for c in chunks]
    metadatas = [c["metadata"] for c in chunks]
    collection.add(ids=ids, documents=documents, embeddings=embeddings, metadatas=metadatas)


def query(kb_id: int, query_embedding: list[float], top_k: int, threshold: float = 0.0) -> list[dict]:
    collection = get_collection(kb_id)
    results = collection.query(query_embeddings=[query_embedding], n_results=top_k)
    chunks = []
    if results["ids"] and results["ids"][0]:
        for i, chunk_id in enumerate(results["ids"][0]):
            score = results["distances"][0][i] if results.get("distances") else 1.0
            if score >= threshold:
                chunks.append({
                    "id": chunk_id,
                    "text": results["documents"][0][i] if results.get("documents") else "",
                    "metadata": results["metadatas"][0][i] if results.get("metadatas") else {},
                    "score": score,
                })
    return chunks


def delete_collection(kb_id: int):
    try:
        _client.delete_collection(name=f"kb_{kb_id}")
    except Exception:
        pass
