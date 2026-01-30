import hashlib
import io
import math
import os
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from agno.knowledge.chunking.fixed import FixedSizeChunking
from agno.knowledge.document.base import Document
from agno.knowledge.embedder.openai import OpenAIEmbedder
from agno.knowledge.reader.pdf_reader import PDFReader
from agno.knowledge.reader.text_reader import TextReader

try:
    from pypdf import PdfReader
except Exception:  # pragma: no cover - handled at runtime
    PdfReader = None


@dataclass
class IndexedChunk:
    text: str
    embedding: List[float]
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class StoredDocument:
    id: str
    name: str
    type: str
    pages: Optional[int] = None
    preview: str = ""
    chunks: List[IndexedChunk] = field(default_factory=list)
    content_hash: Optional[str] = None
    status: str = "indexed"
    message: str = ""


class RagStore:
    def __init__(self) -> None:
        self.docs: Dict[str, StoredDocument] = {}
        self._embedder: Optional[OpenAIEmbedder] = None
        self._chunker = FixedSizeChunking(chunk_size=1200, overlap=200)
        self._pdf_reader = PDFReader(chunking_strategy=self._chunker)
        self._text_reader = TextReader(chunking_strategy=self._chunker)

    def _get_embedder(self) -> Optional[OpenAIEmbedder]:
        if self._embedder is not None:
            return self._embedder
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            return None
        model = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
        self._embedder = OpenAIEmbedder(id=model, api_key=api_key)
        return self._embedder

    def _hash_text(self, text: str) -> str:
        return hashlib.md5(text.encode("utf-8")).hexdigest()

    def _hash_bytes(self, data: bytes) -> str:
        return hashlib.md5(data).hexdigest()

    def _find_by_hash(self, content_hash: str) -> Optional[StoredDocument]:
        for doc in self.docs.values():
            if doc.content_hash == content_hash:
                return doc
        return None

    def _count_pdf_pages(self, data: bytes) -> Optional[int]:
        if PdfReader is None:
            return None
        try:
            return len(PdfReader(io.BytesIO(data)).pages)
        except Exception:
            return None

    def _index_documents(self, stored: StoredDocument, docs: List[Document]) -> None:
        embedder = self._get_embedder()
        chunks: List[IndexedChunk] = []
        for doc in docs:
            text = (doc.content or "").strip()
            if not text:
                continue
            embedding = embedder.get_embedding(text) if embedder else []
            metadata = dict(doc.meta_data or {})
            metadata["doc_id"] = stored.id
            metadata["doc_name"] = stored.name
            chunks.append(IndexedChunk(text=text, embedding=embedding, metadata=metadata))

        stored.chunks = chunks
        if chunks:
            stored.preview = chunks[0].text[:400]

    def index_pdf_bytes(self, data: bytes, filename: str) -> StoredDocument:
        content_hash = self._hash_bytes(data)
        existing = self._find_by_hash(content_hash)
        if existing:
            return existing
        doc_id = str(uuid.uuid4())
        name = os.path.splitext(filename)[0]
        pages = self._count_pdf_pages(data)
        docs = self._pdf_reader.read(io.BytesIO(data), name=name)
        stored = StoredDocument(
            id=doc_id,
            name=name,
            type="PDF",
            pages=pages,
            content_hash=content_hash,
        )
        self._index_documents(stored, docs)
        self.docs[doc_id] = stored
        return stored

    def index_text_bytes(self, data: bytes, filename: str) -> StoredDocument:
        content_hash = self._hash_bytes(data)
        existing = self._find_by_hash(content_hash)
        if existing:
            return existing
        doc_id = str(uuid.uuid4())
        name = os.path.splitext(filename)[0]
        docs = self._text_reader.read(io.BytesIO(data), name=name)
        stored = StoredDocument(id=doc_id, name=name, type="TEXT", content_hash=content_hash)
        self._index_documents(stored, docs)
        self.docs[doc_id] = stored
        return stored

    def index_inline_text(self, doc_id: str, name: str, text: str, doc_type: str = "TEXT") -> StoredDocument:
        content_hash = self._hash_text(text)
        existing = self.docs.get(doc_id)
        if existing and existing.content_hash == content_hash:
            return existing

        docs = self._chunker.chunk(Document(name=name, id=doc_id, content=text))
        stored = StoredDocument(
            id=doc_id,
            name=name,
            type=doc_type,
            pages=existing.pages if existing else None,
            content_hash=content_hash,
        )
        self._index_documents(stored, docs)
        self.docs[doc_id] = stored
        return stored

    def register_stub(self, filename: str, doc_type: str, message: str) -> StoredDocument:
        doc_id = str(uuid.uuid4())
        name = os.path.splitext(filename)[0]
        stored = StoredDocument(
            id=doc_id,
            name=name,
            type=doc_type,
            status="unsupported",
            message=message,
        )
        self.docs[doc_id] = stored
        return stored

    def search(self, query: str, doc_ids: Optional[List[str]] = None, top_k: int = 5) -> List[Dict[str, Any]]:
        query = (query or "").strip()
        if not query:
            return []

        embedder = self._get_embedder()
        query_embedding = embedder.get_embedding(query) if embedder else []
        query_terms = [term.lower() for term in query.split() if term.strip()]

        scored = []
        for doc_id, stored in self.docs.items():
            if doc_ids and doc_id not in doc_ids:
                continue
            for chunk in stored.chunks:
                score = self._score_chunk(chunk, query_embedding, query_terms)
                if score <= 0:
                    continue
                scored.append((score, stored, chunk))

        scored.sort(key=lambda item: item[0], reverse=True)
        results = []
        for score, stored, chunk in scored[: max(top_k, 1)]:
            results.append(
                {
                    "content": chunk.text,
                    "metadata": {
                        "doc_id": stored.id,
                        "doc_name": stored.name,
                        "type": stored.type,
                        "pages": stored.pages,
                        **(chunk.metadata or {}),
                        "score": round(score, 4),
                    },
                }
            )
        return results

    def _score_chunk(
        self, chunk: IndexedChunk, query_embedding: List[float], query_terms: List[str]
    ) -> float:
        if query_embedding and chunk.embedding:
            return self._cosine_similarity(query_embedding, chunk.embedding)
        if not query_terms:
            return 0.0
        text_lower = chunk.text.lower()
        return float(sum(text_lower.count(term) for term in query_terms))

    def _cosine_similarity(self, a: List[float], b: List[float]) -> float:
        if not a or not b:
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(y * y for y in b))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)
