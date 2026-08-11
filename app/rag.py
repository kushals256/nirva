"""RAG store using NVIDIA embeddings + ChromaDB."""

from __future__ import annotations

from typing import Any

import chromadb
import httpx
from chromadb.config import Settings as ChromaSettings
from openai import OpenAI

from app.config import settings
from app.models import Chunk, Citation


class RAGStore:
    def __init__(self) -> None:
        settings.chroma_dir.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(
            path=str(settings.chroma_dir),
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        self._collection = self._client.get_or_create_collection(
            name="pdf_chunks",
            metadata={"hnsw:space": "cosine"},
        )
        self._nvidia = OpenAI(
            api_key=settings.nvidia_api_key,
            base_url=settings.nvidia_base_url,
            http_client=httpx.Client(trust_env=False),
        )

    def _chunk_id(self, doc_id: str, chunk_index: int) -> str:
        return f"{doc_id}:{chunk_index}"

    def _embed(self, texts: list[str], input_type: str = "passage") -> list[list[float]]:
        resp = self._nvidia.embeddings.create(
            model=settings.nvidia_embed_model,
            input=texts,
            extra_body={"input_type": input_type},
        )
        return [item.embedding for item in resp.data]

    def add_chunks(self, chunks: list[Chunk]) -> int:
        if not chunks:
            return 0
        ids = [self._chunk_id(c.doc_id, c.chunk_index) for c in chunks]
        texts = [c.text for c in chunks]
        embeddings = self._embed(texts, input_type="passage")
        metadatas = [
            {"doc_id": c.doc_id, "page": c.page, "chunk_index": c.chunk_index} for c in chunks
        ]
        self._collection.upsert(
            ids=ids, embeddings=embeddings, documents=texts, metadatas=metadatas
        )
        return len(chunks)

    def delete_document(self, doc_id: str) -> None:
        existing = self._collection.get(where={"doc_id": doc_id})
        if existing["ids"]:
            self._collection.delete(ids=existing["ids"])

    def search(self, query: str, doc_id: str | None = None, top_k: int | None = None) -> list[Citation]:
        top_k = top_k or settings.rag_top_k
        query_emb = self._embed([query], input_type="query")[0]
        where: dict[str, Any] | None = {"doc_id": doc_id} if doc_id else None

        results = self._collection.query(
            query_embeddings=[query_emb],
            n_results=top_k,
            where=where,
            include=["documents", "metadatas", "distances"],
        )

        citations: list[Citation] = []
        if not results["documents"] or not results["documents"][0]:
            return citations

        for doc, meta, dist in zip(
            results["documents"][0], results["metadatas"][0], results["distances"][0]
        ):
            score = 1.0 - dist if dist is not None else None
            citations.append(Citation(page=meta["page"], text=doc, score=score))
        return citations


_rag_store: RAGStore | None = None


def get_rag_store() -> RAGStore:
    global _rag_store
    if _rag_store is None:
        _rag_store = RAGStore()
    return _rag_store
