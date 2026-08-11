"""TTS endpoint for text chat (non-WebSocket)."""

from __future__ import annotations

import base64

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.config import settings
from app.voice import _pick_voice, synthesize_speech

router = APIRouter()


class TTSRequest(BaseModel):
    text: str


class TTSResponse(BaseModel):
    audio: str
    format: str = "mp3"
    voice: str


@router.post("/api/tts", response_model=TTSResponse)
async def api_tts(req: TTSRequest) -> TTSResponse:
    if not req.text.strip():
        raise HTTPException(400, "Empty text")
    try:
        audio = await synthesize_speech(req.text)
        return TTSResponse(
            audio=base64.b64encode(audio).decode(),
            voice=_pick_voice(req.text),
        )
    except Exception as e:
        raise HTTPException(500, f"TTS failed: {e}") from e
