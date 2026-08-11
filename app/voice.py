"""Voice pipeline: Deepgram STT → agent → Edge TTS (Indian voices)."""

from __future__ import annotations

import asyncio
import base64
import json
import re

import edge_tts
import httpx
from fastapi import WebSocket, WebSocketDisconnect

from app.agent import chat
from app.config import settings

_active_tasks: dict[int, asyncio.Task | None] = {}


def _pick_voice(text: str) -> str:
    """Use Hindi voice if reply is mostly Devanagari, else Indian English."""
    devanagari = len(re.findall(r"[\u0900-\u097F]", text))
    if devanagari > len(text) * 0.25:
        return settings.tts_voice_hindi
    return settings.tts_voice


async def transcribe_deepgram(audio_bytes: bytes, content_type: str = "audio/webm") -> str:
    if len(audio_bytes) < 500:
        raise ValueError("Recording too short — hold the mic a bit longer.")

    url = "https://api.deepgram.com/v1/listen"
    base_params = {
        "model": settings.deepgram_model,
        "smart_format": "true",
        "punctuate": "true",
    }
    # Try multi first, then fall back if Deepgram rejects the request
    lang_attempts = [settings.deepgram_language, "en-IN", "en-US"]
    headers = {
        "Authorization": f"Token {settings.deepgram_api_key}",
        "Content-Type": content_type.split(";")[0].strip() or "audio/webm",
    }

    last_error = ""
    async with httpx.AsyncClient(timeout=60.0, trust_env=False) as client:
        for lang in lang_attempts:
            params = {**base_params, "language": lang}
            resp = await client.post(url, params=params, headers=headers, content=audio_bytes)
            if resp.status_code == 200:
                data = resp.json()
                return data["results"]["channels"][0]["alternatives"][0]["transcript"].strip()
            last_error = resp.text[:300] or resp.reason_phrase

    raise RuntimeError(f"Deepgram STT failed: {last_error}")


async def synthesize_speech(text: str) -> bytes:
    """Natural Indian English/Hindi TTS via Microsoft Edge neural voices."""
    short = text[:500] if len(text) > 500 else text
    voice = _pick_voice(short)
    communicate = edge_tts.Communicate(short, voice)
    audio = bytearray()
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio.extend(chunk["data"])
    return bytes(audio)


async def _send_reply_with_audio(websocket: WebSocket, result, conn_id: int) -> None:
    await websocket.send_json(
        {
            "type": "reply",
            "session_id": result.session_id,
            "text": result.reply,
            "answer_detail": result.answer_detail,
            "citations": [c.model_dump() for c in result.citations],
            "tool_calls": [t.model_dump() for t in result.tool_calls],
            "code_blocks": result.code_blocks,
        }
    )

    if not result.reply:
        await websocket.send_json({"type": "status", "status": "idle"})
        return

    async def _speak() -> None:
        try:
            await websocket.send_json({"type": "status", "status": "speaking"})
            audio = await synthesize_speech(result.reply)
            await websocket.send_json(
                {
                    "type": "audio_out",
                    "audio": base64.b64encode(audio).decode(),
                    "format": "mp3",
                    "voice": _pick_voice(result.reply),
                }
            )
            await websocket.send_json({"type": "status", "status": "idle"})
        except asyncio.CancelledError:
            await websocket.send_json({"type": "status", "status": "idle"})
            raise

    task = asyncio.create_task(_speak())
    _active_tasks[conn_id] = task
    try:
        await task
    except asyncio.CancelledError:
        pass


async def handle_voice_websocket(
    websocket: WebSocket, session_id: str | None, doc_id: str | None
) -> None:
    await websocket.accept()
    conn_id = id(websocket)
    _active_tasks[conn_id] = None

    try:
        while True:
            raw = await websocket.receive_text()
            payload = json.loads(raw)
            msg_type = payload.get("type")

            if msg_type == "cancel":
                task = _active_tasks.get(conn_id)
                if task and not task.done():
                    task.cancel()
                await websocket.send_json({"type": "cancelled"})
                continue

            if msg_type == "audio":
                audio_b64 = payload.get("audio", "")
                audio_bytes = base64.b64decode(audio_b64)
                content_type = payload.get("content_type", "audio/webm")
                sid = payload.get("session_id") or session_id
                did = payload.get("doc_id") or doc_id

                await websocket.send_json({"type": "status", "status": "transcribing"})
                try:
                    transcript = await transcribe_deepgram(audio_bytes, content_type)
                except Exception as e:
                    await websocket.send_json(
                        {"type": "error", "message": f"STT failed: {e}. Try typing instead, or hold mic longer."}
                    )
                    await websocket.send_json({"type": "status", "status": "idle"})
                    continue

                await websocket.send_json({"type": "transcript", "text": transcript})
                if not transcript:
                    await websocket.send_json({"type": "error", "message": "Empty transcript"})
                    continue

                await websocket.send_json({"type": "status", "status": "thinking"})
                try:
                    result = await asyncio.to_thread(chat, sid, transcript, did)
                    await _send_reply_with_audio(websocket, result, conn_id)
                except Exception as e:
                    await websocket.send_json({"type": "error", "message": f"Chat failed: {e}"})
                    await websocket.send_json({"type": "status", "status": "idle"})

            elif msg_type == "text":
                text = payload.get("text", "")
                sid = payload.get("session_id") or session_id
                did = payload.get("doc_id") or doc_id

                await websocket.send_json({"type": "status", "status": "thinking"})
                try:
                    result = await asyncio.to_thread(chat, sid, text, did)
                    await _send_reply_with_audio(websocket, result, conn_id)
                except Exception as e:
                    await websocket.send_json({"type": "error", "message": f"Chat failed: {e}"})
                    await websocket.send_json({"type": "status", "status": "idle"})

    except WebSocketDisconnect:
        pass
    finally:
        task = _active_tasks.pop(conn_id, None)
        if task and not task.done():
            task.cancel()
