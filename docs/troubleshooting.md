# Troubleshooting

## `/health` is fine, chat is empty or “no document”

Upload first. Tools refuse to invent a PDF. On Render **free tier** there is no persistent disk in `render.yaml` — after sleep/recycle, `data/` (uploads + Chroma) is gone. Re-upload, or add a disk mounted on the service so `data/` survives.

## First request after idle takes ~50 seconds

The API is on Render free tier. It sleeps. The next voice or chat turn pays cold start. Text `curl /health` once before a demo.

## Reply talks about `search_pdf` or “I’ll call the function”

The model leaked the tool surface. The agent tries to reject that and fill from citations. Ask again, or use a page-specific question (“what’s on page 2”).

## English question, Hinglish answer (or the reverse)

Language is supposed to follow the student turn. If it drifts, say the language in the question once (“answer in English”). Persistent mix is a known 8B failure mode the filters only partly catch.

## Mic: “recording too short”

Hold the button longer. Deepgram rejects tiny blobs (`< 500` bytes).

## Mic: WebSocket closes immediately

`NVIDIA_API_KEY` or `DEEPGRAM_API_KEY` missing in the **API** process, not only in Vercel. Voice needs both.

## Mic: “Mic permission denied”

Browser blocked the microphone. Allow it for `localhost` / the Vercel origin.

## `run_command` not allowed / timed out

Only `python`, `python3`, `pytest`. Timeout is set in config. Commands run in `workspace/` only.

## Patch didn’t change my file

By design. `propose_patch` returns a diff with `applied: false`. The student applies it.

## Frontend works, API CORS errors

Set `CORS_ORIGINS` to the exact Vercel origin (scheme + host, no trailing path). Rebuild/redeploy the API after changing env.

## Local UI still points at production

Copy `frontend/config.example.js` → `frontend/config.js`. For local FastAPI, keep `API_BASE: ""` (same origin). Vercel injects `NIRVA_API_URL` at build time via `scripts/inject-config.js`; a stale `config.js` in the repo will not pick up `.env`.
