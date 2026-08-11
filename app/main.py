"""FastAPI app: PDF upload, chat, voice WebSocket, static frontend."""

from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.agent import chat, get_session
from app.config import settings
from app.models import ChatRequest, ChatResponse, UploadResponse
from app.pdf_ingest import (
    extract_pages,
    ingest_pdf,
    list_documents,
    load_document_meta,
    save_document_meta,
    save_pages_cache,
)
from app.rag import get_rag_store
from app.tools import set_current_doc
from app.tts import router as tts_router
from app.voice import handle_voice_websocket

app = FastAPI(title="Hinglish Voice Coding Tutor", version="0.1.0")
app.include_router(tts_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"


@app.on_event("startup")
async def startup() -> None:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.workspace_dir.mkdir(parents=True, exist_ok=True)
    (settings.data_dir / "uploads").mkdir(parents=True, exist_ok=True)


@app.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "llm": settings.nvidia_llm_model,
        "embed": settings.nvidia_embed_model,
        "stt": settings.deepgram_model,
        "tts": settings.tts_voice,
    }


@app.get("/api/documents")
async def api_list_documents() -> dict:
    return {"documents": [d.model_dump(mode="json") for d in list_documents()]}


@app.post("/api/upload", response_model=UploadResponse)
async def upload_pdf(file: UploadFile = File(...)) -> UploadResponse:
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Only PDF files are supported")

    upload_path = settings.data_dir / "uploads" / file.filename
    with upload_path.open("wb") as f:
        shutil.copyfileobj(file.file, f)

    document, chunks = ingest_pdf(upload_path, filename=file.filename)
    pages = extract_pages(upload_path)
    save_pages_cache(document.id, pages)
    save_document_meta(document)

    store = get_rag_store()
    store.delete_document(document.id)
    if chunks:
        store.add_chunks(chunks)

    set_current_doc(document.id)
    preview = [{"page": p["page"], "preview": p["text"][:200]} for p in pages[:5]]
    return UploadResponse(document=document, pages_preview=preview)


@app.get("/api/documents/{doc_id}/pages")
async def get_document_pages(doc_id: str) -> dict:
    doc = load_document_meta(doc_id)
    if not doc:
        raise HTTPException(404, "Document not found")
    upload_path = settings.data_dir / "uploads" / doc.filename
    if not upload_path.exists():
        raise HTTPException(404, "PDF file missing on disk")
    pages = extract_pages(upload_path)
    return {"document": doc.model_dump(mode="json"), "pages": pages}


@app.post("/api/chat", response_model=ChatResponse)
async def api_chat(req: ChatRequest) -> ChatResponse:
    if not settings.nvidia_api_key:
        raise HTTPException(500, "NVIDIA_API_KEY not configured")
    doc_id = req.doc_id
    if req.session_id and not doc_id:
        doc_id = get_session(req.session_id).doc_id
    return chat(req.session_id, req.message, doc_id=doc_id)


@app.get("/api/sessions/{session_id}")
async def api_get_session(session_id: str) -> dict:
    return get_session(session_id).model_dump(mode="json")


@app.websocket("/ws/voice")
async def ws_voice(
    websocket: WebSocket, session_id: str | None = None, doc_id: str | None = None
) -> None:
    if not settings.nvidia_api_key or not settings.deepgram_api_key:
        await websocket.close(code=1011, reason="API keys not configured")
        return
    await handle_voice_websocket(websocket, session_id, doc_id)


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "index.html")


if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")
