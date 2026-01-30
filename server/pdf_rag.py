import io
import os
import uuid
from typing import List, Tuple

try:
    import PyPDF2
except Exception:
    PyPDF2 = None

try:
    import numpy as np
except Exception:
    np = None

from openai import OpenAI

# Simple in-memory vector store: doc_id -> list of {chunk_id, text, embedding}
VECTOR_STORE = {}


def extract_text_from_pdf_bytes(data: bytes) -> Tuple[str, int]:
    if PyPDF2 is None:
        raise RuntimeError("PyPDF2 未安裝，無法解析 PDF。請先安裝 PyPDF2。")
    reader = PyPDF2.PdfReader(io.BytesIO(data))
    pages = len(reader.pages)
    texts = []
    for p in reader.pages:
        try:
            texts.append(p.extract_text() or "")
        except Exception:
            texts.append("")
    return "\n\n".join(texts), pages


def chunk_text(text: str, chunk_size: int = 1200, overlap: int = 200) -> List[str]:
    if not text:
        return []
    chunks = []
    start = 0
    length = len(text)
    while start < length:
        end = min(start + chunk_size, length)
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        start = end - overlap
        if start < 0:
            start = 0
    return chunks


def get_openai_client() -> OpenAI:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None
    return OpenAI(api_key=api_key)


def compute_embeddings(client: OpenAI, texts: List[str]) -> List[List[float]]:
    model = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
    if not texts:
        return []
    if client is None:
        # No API key available — return empty embeddings placeholders
        return [[] for _ in texts]
    resp = client.embeddings.create(model=model, input=texts)
    return [item.embedding for item in resp.data]


def cosine_similarity(a, b):
    if np is None:
        raise RuntimeError("numpy 未安裝，無法計算相似度。請先安裝 numpy。")
    a = np.array(a, dtype=float)
    b = np.array(b, dtype=float)
    if np.linalg.norm(a) == 0 or np.linalg.norm(b) == 0:
        return 0.0
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


def store_pdf_bytes(file_bytes: bytes, filename: str):
    """Parse PDF bytes, chunk and embed, store into VECTOR_STORE, return doc metadata."""
    client = get_openai_client()
    text, pages = extract_text_from_pdf_bytes(file_bytes)
    chunks = chunk_text(text)
    embeddings = compute_embeddings(client, chunks) if chunks else []
    doc_id = str(uuid.uuid4())
    items = []
    for idx, (chunk, emb) in enumerate(zip(chunks, embeddings)):
        items.append({"chunk_id": f"{doc_id}-{idx}", "text": chunk, "embedding": emb})
    VECTOR_STORE[doc_id] = items
    return {"id": doc_id, "name": filename, "type": "PDF", "pages": pages}


def retrieve_similar(doc_id: str, query: str, top_k: int = 3) -> List[dict]:
    client = get_openai_client()
    items = VECTOR_STORE.get(doc_id) or []
    if not items:
        return []
    q_emb = compute_embeddings(client, [query])[0]
    scored = []
    for it in items:
        score = cosine_similarity(q_emb, it["embedding"])
        scored.append((score, it))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [it for _, it in scored[:top_k]]
