# API reference

Base URL: `http://localhost:8000` locally, `https://nirva-api.onrender.com` in prod.

CORS is set from `CORS_ORIGINS`. The Vercel frontend must be on that list.

## `GET /health`

Liveness + which models the process loaded.

```bash
curl -s http://localhost:8000/health
```

```json
{
  "status": "ok",
  "llm": "meta/llama-3.1-8b-instruct",
  "embed": "nvidia/nv-embedqa-e5-v5",
  "stt": "nova-3",
  "tts": "en-IN-NeerjaNeural"
}
```

## `POST /api/upload`

`multipart/form-data` field `file`. PDF only.

```bash
curl -s -F "file=@assignment.pdf" http://localhost:8000/api/upload
```

Returns `document.id`, `pages`, a short preview of the first pages, and suggested prompts. Keep `document.id` — chat and voice both need it.

## `GET /api/documents`

Lists uploads this process still has. Empty after a diskless Render recycle.

## `GET /api/documents/{doc_id}/pages`

Full extracted page text. `404` if the id is unknown or the PDF file is gone from disk.

## `POST /api/chat`

```json
{
  "message": "What is the input format?",
  "session_id": null,
  "doc_id": "uuid-from-upload"
}
```

| Field | Required | Notes |
|---|---|---|
| `message` | yes | Student text |
| `session_id` | no | Omit to start a session; reuse to keep turn history |
| `doc_id` | no | Bind this PDF. If omitted, uses the session’s doc or the **process-global last upload** |

`500` if `NVIDIA_API_KEY` is missing.

Response includes `session_id`, `reply`, `citations[]` (`page`, `text`, `score`), `tool_calls[]`, and any `code_blocks` pulled from tools.

## `GET /api/sessions/{session_id}`

Returns that in-memory session. If the id is unknown, **a new session is created** (new id). Don’t treat this as a strict lookup.

## `POST /api/tts`

Speak a reply that already exists as text.

```json
{ "text": "Page 2 lists the starter files." }
```

Returns base64 `audio` (`mp3`) and which `voice` was used (Indian English vs Hindi, from script mix).

## `WS /ws/voice`

Optional query: `session_id`, `doc_id`. Same fields can also ride on each JSON message. Closes with `1011` before accept if NVIDIA or Deepgram is missing.

Client → server (JSON text, not raw binary):

| `type` | Body |
|---|---|
| `audio` | `audio` (base64), `content_type` (default `audio/webm`), optional `session_id` / `doc_id` |
| `text` | `text`, optional ids |
| `cancel` | Stop in-flight TTS |

Server → client: `status` (`transcribing` / `thinking` / `speaking` / `idle`), `transcript`, `reply` (full chat payload), `audio_out` (base64 mp3), `error`, `cancelled`.

## Errors you will actually hit

| Status / close | Meaning |
|---|---|
| `400` on upload | Not a `.pdf` |
| `400` on TTS | Empty `text` |
| `500` on chat | `NVIDIA_API_KEY` not set |
| `404` on pages | Unknown `doc_id` or PDF missing on disk |
| `1011` on voice WS | NVIDIA or Deepgram missing |
| Chat `citations: []` | No retrieval — upload first, or the index was wiped |
| Tool result `Path escapes workspace` | `read_workspace_file` / patch left `workspace/` |
