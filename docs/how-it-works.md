# How it works

Nirva is a **tool-calling tutor**, not a chatbot that “has the PDF in context.”

```
mic or text
    → session (chat history + bound doc_id)
    → Llama 3.1 8B (NVIDIA NIM), up to 6 tool rounds
    → tools (PDF RAG, workspace, sandbox)
    → spoken or typed reply with page citations
```

## Agent loop

Each user turn:

1. Detect intent: whole-PDF walkthrough, a specific page, code/error, or a short “ok do it.”
2. Call tools. Overview and “page N” questions are forced in code (`summarize_pdf` / `get_page`). Other PDF questions are instructed to retrieve first; that is prompt + leak filters, not a hard lock.
3. Feed tool JSON back into the model. Max **6** rounds. The prompt window is the last **20** session messages.
4. Speak. Strip tool-name leaks. If the model says “I’ll call `search_pdf`” instead of answering, that reply is rejected and filled from citations when possible.

Language is routing, not style: Hinglish in → Hinglish out; English in → English only.

## Tools

| Tool | Does | Will not |
|---|---|---|
| `search_pdf` | Top-k chunks + page numbers (Chroma + NVIDIA E5) | Invent a page |
| `get_page` | Full text of page *n* | Guess *n* |
| `quote_requirement` | Best matching snippet; empty → “do not invent” | Fabricate a constraint |
| `summarize_pdf` | Every page (overviews / walkthroughs) | Summarize a missing upload |
| `read_workspace_file` | Read under `workspace/` | Path escape |
| `run_command` | `python` / `pytest` only, timeout, cwd = workspace | Arbitrary shell |
| `propose_patch` | Unified diff | Write the student’s file (`applied: false`) |

## Memory

| Layer | What it is | Survives restart? |
|---|---|---|
| Session | Messages + `doc_id` in process RAM | No |
| Task | Uploaded PDF chunks in Chroma; files in `workspace/` | Local yes. Render free tier: **no** (no disk) |
| Chat-as-PDF | Not used — the file is retrieved, not replayed | — |

If `doc_id` is missing, tools return an error. That is a product failure, not a model miss.

## Voice path

1. Browser opens `WS /ws/voice` and sends **JSON text** frames (`type: audio` with base64 webm, or `type: text` / `cancel`).
2. Deepgram Nova-3 (`language=multi`, then `en-IN` / `en-US` if rejected).
3. Same `chat()` as `POST /api/chat`.
4. Server replies with JSON: `reply`, then `audio_out` (base64 mp3). Edge TTS: Indian English, or Hindi if the reply is mostly Devanagari.

There is no second agent for voice. Mic and typed box share the session.

## Production limits (honest)

- Render free tier sleeps the API (~50s first hit after idle).
- Without a persistent disk, Chroma and uploads vanish when the instance recycles.
- STT + 6 tool rounds + TTS is slower than text-only. That is expected.
