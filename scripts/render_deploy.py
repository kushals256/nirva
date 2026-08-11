#!/usr/bin/env python3
"""Create Render web service and set env vars for Nirva backend."""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CLI_CONFIG = Path.home() / ".render" / "cli.yaml"
ENV_FILE = ROOT / ".env"
OWNER_ID = "tea-d9tdc9ajobas73cmqb60"
API_BASE = "https://api.render.com/v1"


def load_api_key() -> str:
    text = CLI_CONFIG.read_text()
    for line in text.splitlines():
        if line.strip().startswith("key:"):
            return line.split(":", 1)[1].strip()
    raise SystemExit("Render API key not found in ~/.render/cli.yaml")


def load_env() -> dict[str, str]:
    values: dict[str, str] = {}
    if not ENV_FILE.exists():
        return values
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        values[key.strip()] = val.strip()
    return values


def request(method: str, path: str, api_key: str, payload: dict | None = None) -> dict:
    data = None
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
    }
    if payload is not None:
        data = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(f"{API_BASE}{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            body = resp.read().decode()
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode()
        raise SystemExit(f"{method} {path} failed ({exc.code}): {detail}") from exc


def find_existing_service(api_key: str, name: str) -> dict | None:
    cursor = ""
    while True:
        suffix = f"?limit=100&name={name}" if not cursor else f"?limit=100&cursor={cursor}&name={name}"
        items = request("GET", f"/services{suffix}", api_key)
        if not isinstance(items, list):
            break
        for item in items:
            svc = item.get("service") or item
            if svc.get("name") == name:
                return svc
        if not items:
            break
        cursor = items[-1].get("cursor", "")
        if not cursor:
            break
    return None


def create_service(api_key: str) -> dict:
    payload = {
        "type": "web_service",
        "name": "nirva-api",
        "ownerId": OWNER_ID,
        "repo": "https://github.com/kushals256/nirva",
        "branch": "main",
        "autoDeploy": "yes",
        "serviceDetails": {
            "runtime": "python",
            "plan": "free",
            "healthCheckPath": "/health",
            "envSpecificDetails": {
                "buildCommand": "pip install -r requirements.txt",
                "startCommand": "uvicorn app.main:app --host 0.0.0.0 --port $PORT",
            },
        },
    }
    return request("POST", "/services", api_key, payload)


def set_env_vars(api_key: str, service_id: str, env: dict[str, str]) -> None:
    local = load_env()
    merged = {
        "NVIDIA_BASE_URL": local.get("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1"),
        "NVIDIA_LLM_MODEL": local.get("NVIDIA_LLM_MODEL", "meta/llama-3.1-8b-instruct"),
        "NVIDIA_EMBED_MODEL": local.get("NVIDIA_EMBED_MODEL", "nvidia/nv-embedqa-e5-v5"),
        "DEEPGRAM_MODEL": local.get("DEEPGRAM_MODEL", "nova-3"),
        "DEEPGRAM_LANGUAGE": local.get("DEEPGRAM_LANGUAGE", "multi"),
        "TTS_VOICE": local.get("TTS_VOICE", "en-IN-NeerjaNeural"),
        "TTS_VOICE_HINDI": local.get("TTS_VOICE_HINDI", "hi-IN-SwaraNeural"),
        "CORS_ORIGINS": "https://nirva-seven.vercel.app,http://localhost:8000,http://127.0.0.1:8000",
        "NVIDIA_API_KEY": local.get("NVIDIA_API_KEY", ""),
        "DEEPGRAM_API_KEY": local.get("DEEPGRAM_API_KEY", ""),
    }
    merged.update({k: v for k, v in env.items() if v})
    env_vars = [{"key": k, "value": v} for k, v in merged.items() if v]
    request("PUT", f"/services/{service_id}/env-vars", api_key, env_vars)


def trigger_deploy(api_key: str, service_id: str) -> dict:
    return request("POST", f"/services/{service_id}/deploys", api_key, {"clearCache": "do_not_clear"})


def main() -> None:
    api_key = load_api_key()
    existing = find_existing_service(api_key, "nirva-api")
    if existing:
        service = existing
        print(f"Using existing service: {service['id']}")
    else:
        created = create_service(api_key)
        service = created.get("service", created)
        print(f"Created service: {service['id']}")

    service_id = service["id"]
    set_env_vars(api_key, service_id, {})
    trigger_deploy(api_key, service_id)

    url = service.get("serviceDetails", {}).get("url") or service.get("url")
    print(json.dumps({"service_id": service_id, "url": url}, indent=2))


if __name__ == "__main__":
    main()
