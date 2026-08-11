# Nirva — Hinglish Voice Coding Tutor

Upload an assignment PDF, talk in English/Hinglish, get grounded answers with page citations + coding tool help.

## Stack

| Layer | Provider |
|---|---|
| LLM + tool calling | NVIDIA NIM (`meta/llama-3.1-8b-instruct`) |
| Embeddings | NVIDIA NIM (`nvidia/nv-embedqa-e5-v5`) |
| STT | Deepgram Nova-3 (`language=multi`) |
| TTS | Edge TTS (Indian voices) |
| Vector store | ChromaDB (local) |
| Backend | FastAPI on Render |
| Frontend | Static SPA on Vercel |

## Quick start (local)

```bash
cd nirva
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env   # add your API keys
cp frontend/config.example.js frontend/config.js

python scripts/generate_sample_pdf.py   # optional
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Open http://localhost:8000

## Deploy

### 1. Backend → Render

1. Push this repo to GitHub
2. [Render](https://render.com) → New Web Service → connect repo
3. Use `render.yaml` or set:
   - **Build:** `pip install -r requirements.txt`
   - **Start:** `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
4. Add env vars: `NVIDIA_API_KEY`, `DEEPGRAM_API_KEY`
5. Set `CORS_ORIGINS` to your Vercel URL (e.g. `https://nirva.vercel.app`)
6. Add a **persistent disk** mounted at `/opt/render/project/src/data` for PDF + Chroma storage

### 2. Frontend → Vercel

1. Import the GitHub repo on [Vercel](https://vercel.com)
2. Framework preset: **Other**
3. Root directory: `.` (uses `vercel.json`)
4. Add environment variable:
   - `NIRVA_API_URL` = your Render backend URL (e.g. `https://voice-coding-tutor.onrender.com`)
5. Deploy

The build runs `scripts/inject-config.js` to wire the frontend to your backend.

## Tools

1. `search_pdf(query)` — RAG search with page numbers
2. `get_page(page_n)` — full page text
3. `quote_requirement(topic)` — must-cite snippet
4. `summarize_pdf()` — full PDF walkthrough
5. `read_workspace_file(path)` — read student code
6. `run_command(cmd)` — sandboxed pytest/python
7. `propose_patch(...)` — diff suggestion (not auto-applied)

## API keys

See `.env.example`. **Never commit `.env`. Rotate keys if exposed.**
