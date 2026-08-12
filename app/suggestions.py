"""Personalized 'Try asking' prompts from uploaded PDF content."""

from __future__ import annotations

import json
import re
from typing import Any

import httpx
from openai import OpenAI

from app.config import settings

DEFAULT_PROMPTS = [
    "whats in the pdf?",
    "constraints kya hain?",
    "input format kya hai?",
    "summarize the assignment",
]

_SUGGESTION_SYSTEM = """You suggest starter questions for a student chatting with an AI tutor about THEIR uploaded PDF.

Return ONLY a JSON array of exactly 4 strings — no markdown, no explanation.
Rules:
- Each question: short (max 45 characters), specific to THIS document.
- Mix ~2 English and ~2 Hinglish (Roman script) when it fits the doc type.
- Coding assignments: structure, constraints, input/output, debugging.
- Presentations/reports: topic, experiments, key findings, methodology.
- Rosters/directories: what it lists, how it's organized — NOT generic coding questions.
- Never mention tools, PDF pages literally, or "the document says"."""


def _sample_text(pages: list[dict[str, Any]], max_chars: int = 2500) -> str:
    parts: list[str] = []
    total = 0
    for p in pages[:8]:
        text = re.sub(r"\s+", " ", (p.get("text") or "")).strip()
        if not text:
            continue
        chunk = text[:400]
        parts.append(chunk)
        total += len(chunk)
        if total >= max_chars:
            break
    return " ".join(parts)


def _heuristic_prompts(pages: list[dict[str, Any]], filename: str) -> list[str]:
    sample = _sample_text(pages).lower()
    name = (filename or "").lower()
    n = len(pages)
    picks: list[str] = []

    is_roster = bool(re.search(r"student name|email id|@\S+\.\S+|house\b", sample))
    is_ml = bool(re.search(r"cifar|experiment|optimizer|batch size|neural network|cnn", sample))
    is_pres = bool(re.search(r"agenda|slide|presentation|methodology|results", sample))
    is_code = bool(re.search(r"def |class |pytest|input format|constraint|main\.py|starter", sample))

    if is_roster:
        picks.extend([
            "ye pdf kis baare mein hai?",
            "kitne entries listed hain?",
            "house info kahan hai?",
            f"summary of all {n} pages",
        ])
    elif is_ml or is_pres:
        picks.extend([
            "project ka main topic kya hai?",
            "experiments ka overview do",
            "key findings kya hain?",
            "methodology explain karo",
        ])
    elif is_code:
        picks.extend([
            "starter structure kya hona chahiye?",
            "input format kya hai?",
            "constraints kya hain?",
            "pytest error debug karo",
        ])
    else:
        picks.extend([
            "whats in the pdf?",
            "give me a summary",
            "main topic kya hai?",
            "explain page 1",
        ])

    if "task" in sample or "assignment" in sample or "assignment" in name:
        if "deliverables kya hain?" not in picks:
            picks.append("deliverables kya hain?")
    if "deadline" in sample or "due" in sample:
        picks.append("deadline kab hai?")

    seen: set[str] = set()
    unique: list[str] = []
    for q in picks:
        key = q.lower().strip()
        if key not in seen:
            seen.add(key)
            unique.append(q)
        if len(unique) >= 4:
            break

    while len(unique) < 4:
        for fallback in DEFAULT_PROMPTS:
            if fallback.lower() not in seen:
                unique.append(fallback)
                seen.add(fallback.lower())
            if len(unique) >= 4:
                break
        break

    return unique[:4]


def _parse_prompts_json(raw: str) -> list[str] | None:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\[[\s\S]*\]", raw)
        if not match:
            return None
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
    if not isinstance(data, list):
        return None
    prompts = [str(x).strip() for x in data if str(x).strip()]
    return prompts[:4] if len(prompts) >= 2 else None


def generate_suggested_prompts(
    pages: list[dict[str, Any]],
    filename: str = "",
) -> list[str]:
    """Return 4 chat prompts tailored to the uploaded PDF."""
    if not pages:
        return DEFAULT_PROMPTS.copy()

    if settings.nvidia_api_key:
        outline = "\n".join(
            f"Page {p['page']}: {re.sub(r'\\s+', ' ', (p.get('text') or ''))[:300]}"
            for p in pages[:6]
            if p.get("text")
        )
        try:
            client = OpenAI(
                api_key=settings.nvidia_api_key,
                base_url=settings.nvidia_base_url,
                http_client=httpx.Client(trust_env=False),
            )
            resp = client.chat.completions.create(
                model=settings.nvidia_llm_model,
                messages=[
                    {"role": "system", "content": _SUGGESTION_SYSTEM},
                    {
                        "role": "user",
                        "content": f'Filename: "{filename}"\nPages: {len(pages)}\n\n{outline}',
                    },
                ],
                temperature=0.4,
                max_tokens=220,
            )
            raw = resp.choices[0].message.content or ""
            parsed = _parse_prompts_json(raw)
            if parsed and len(parsed) >= 4:
                return [p[:60] for p in parsed[:4]]
            if parsed:
                merged = parsed + _heuristic_prompts(pages, filename)
                seen: set[str] = set()
                out: list[str] = []
                for q in merged:
                    k = q.lower()
                    if k not in seen:
                        seen.add(k)
                        out.append(q)
                    if len(out) >= 4:
                        break
                return out[:4]
        except Exception:
            pass

    return _heuristic_prompts(pages, filename)
