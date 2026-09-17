# Quickstart

Run Nirva locally, upload a PDF, ask a question. Voice is optional for the first check.

## You need

- Python 3.10+
- `NVIDIA_API_KEY` (required for chat)
- `DEEPGRAM_API_KEY` (required for the mic; text chat works without it)

## Install

```bash
git clone https://github.com/kushals256/nirva.git
cd nirva
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # fill NVIDIA_API_KEY (and Deepgram if you use voice)
cp frontend/config.example.js frontend/config.js
```

Leave `API_BASE` as `""` in `config.js`. The UI then talks to the same origin FastAPI is serving (`http://localhost:8000`).

## Run

```bash
python scripts/generate_sample_pdf.py   # optional assignment PDF
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Open [http://localhost:8000/tutor](http://localhost:8000/tutor).

Sanity check without the UI:

```bash
curl -s http://localhost:8000/health
```

You should see `"status": "ok"` and the configured model names. `/health` does **not** check that the NVIDIA key works — a missing key still returns 200. Chat is what fails (`500 NVIDIA_API_KEY not configured`).

## First call (text)

```bash
# 1. Upload (file is written to the repo root by the sample script)
curl -s -F "file=@sample_assignment.pdf" http://localhost:8000/api/upload | python -m json.tool

# 2. Chat — paste doc_id from the upload response
curl -s http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"Summarize the assignment","doc_id":"YOUR_DOC_ID"}'
```

A good reply names a **page number**. If it talks about `search_pdf()` instead of the PDF, that turn failed the agent’s own checks — try again or see [troubleshooting](troubleshooting.md).

## Voice

Hold the mic on `/tutor`. Flow: browser audio → `/ws/voice` → Deepgram Nova-3 → same chat agent → Edge TTS (Indian English or Hindi).

Skip voice until text chat works. The voice socket closes immediately if either NVIDIA or Deepgram is missing.

## What “done” looks like

| You did | You should see |
|---|---|
| `GET /health` | `"status": "ok"` |
| Upload PDF | `document.id` and page previews |
| Chat about the PDF | `citations` with `page` ≥ 1 |
| Mic question | Spoken reply, same citations in the UI |
