"""PDF ingestion: extract text with page numbers and chunk for RAG."""

from __future__ import annotations

import json
from pathlib import Path

import fitz

from app.config import settings
from app.models import Chunk, Document, new_id


def extract_pages(pdf_path: Path) -> list[dict]:
    doc = fitz.open(pdf_path)
    pages = []
    for i in range(len(doc)):
        text = doc[i].get_text("text").strip()
        pages.append({"page": i + 1, "text": text})
    doc.close()
    return pages


def chunk_text(text: str, page: int, doc_id: str, start_index: int = 0) -> list[Chunk]:
    size = settings.chunk_size
    overlap = settings.chunk_overlap
    chunks: list[Chunk] = []
    if not text:
        return chunks

    start = 0
    idx = start_index
    while start < len(text):
        end = start + size
        piece = text[start:end].strip()
        if piece:
            chunks.append(Chunk(doc_id=doc_id, page=page, text=piece, chunk_index=idx))
            idx += 1
        if end >= len(text):
            break
        start = end - overlap
    return chunks


def ingest_pdf(pdf_path: Path, filename: str | None = None) -> tuple[Document, list[Chunk]]:
    pages = extract_pages(pdf_path)
    doc = Document(id=new_id(), filename=filename or pdf_path.name, pages=len(pages))

    all_chunks: list[Chunk] = []
    chunk_idx = 0
    for page_data in pages:
        page_chunks = chunk_text(page_data["text"], page_data["page"], doc.id, chunk_idx)
        all_chunks.extend(page_chunks)
        chunk_idx += len(page_chunks)

    return doc, all_chunks


def save_document_meta(doc: Document) -> None:
    docs_dir = settings.data_dir / "documents"
    docs_dir.mkdir(parents=True, exist_ok=True)
    (docs_dir / f"{doc.id}.json").write_text(doc.model_dump_json(indent=2))


def load_document_meta(doc_id: str) -> Document | None:
    path = settings.data_dir / "documents" / f"{doc_id}.json"
    if not path.exists():
        return None
    return Document.model_validate_json(path.read_text())


def list_documents() -> list[Document]:
    docs_dir = settings.data_dir / "documents"
    if not docs_dir.exists():
        return []
    docs = []
    for path in docs_dir.glob("*.json"):
        try:
            docs.append(Document.model_validate_json(path.read_text()))
        except Exception:
            continue
    return sorted(docs, key=lambda d: d.created_at, reverse=True)


def save_pages_cache(doc_id: str, pages: list[dict]) -> None:
    cache_dir = settings.data_dir / "pages"
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / f"{doc_id}.json").write_text(json.dumps(pages, ensure_ascii=False, indent=2))


def load_pages_cache(doc_id: str) -> list[dict]:
    path = settings.data_dir / "pages" / f"{doc_id}.json"
    if not path.exists():
        return []
    return json.loads(path.read_text())
