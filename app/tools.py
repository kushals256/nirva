"""Six agent tools for PDF RAG and workspace coding help."""

from __future__ import annotations

import difflib
import json
import re
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

from app.config import settings
from app.models import Citation
from app.pdf_ingest import load_pages_cache
from app.rag import get_rag_store

_current_doc_id: str | None = None


def set_current_doc(doc_id: str | None) -> None:
    global _current_doc_id
    _current_doc_id = doc_id


def get_current_doc() -> str | None:
    return _current_doc_id


def _command_env() -> dict[str, str]:
    """PATH includes the active Python venv so pytest/python resolve correctly."""
    venv_bin = str(Path(sys.executable).resolve().parent)
    path = ":".join(dict.fromkeys([venv_bin, "/usr/local/bin", "/usr/bin", "/bin"]))
    return {"PATH": path, "HOME": str(settings.workspace_dir.resolve())}


def _resolve_command(parts: list[str]) -> list[str]:
    """Map python/pytest to the current interpreter's venv when possible."""
    if not parts:
        return parts
    binary = Path(parts[0]).name
    venv_bin = Path(sys.executable).resolve().parent
    if binary in {"python", "python3"}:
        return [sys.executable, *parts[1:]]
    if binary == "pytest":
        pytest = venv_bin / "pytest"
        if pytest.exists():
            return [str(pytest), *parts[1:]]
        return [sys.executable, "-m", "pytest", *parts[1:]]
    return parts


def _resolve_workspace_path(path: str) -> Path:
    workspace = settings.workspace_dir.resolve()
    target = (workspace / path).resolve()
    if not str(target).startswith(str(workspace)):
        raise ValueError(f"Path escapes workspace: {path}")
    return target


def search_pdf(query: str, doc_id: str | None = None) -> dict[str, Any]:
    doc_id = doc_id or _current_doc_id
    if not doc_id:
        return {"error": "No document loaded. Upload a PDF first.", "results": []}

    citations = get_rag_store().search(query, doc_id=doc_id)
    results = [
        {
            "page": c.page,
            "text": c.text[:500],
            "score": round(c.score, 3) if c.score is not None else None,
        }
        for c in citations
    ]
    return {"query": query, "doc_id": doc_id, "results": results}


def get_page(page_n: int, doc_id: str | None = None) -> dict[str, Any]:
    doc_id = doc_id or _current_doc_id
    if not doc_id:
        return {"error": "No document loaded.", "page": page_n, "text": ""}

    for p in load_pages_cache(doc_id):
        if p["page"] == page_n:
            return {"page": page_n, "text": p["text"], "doc_id": doc_id}
    return {"error": f"Page {page_n} not found.", "page": page_n, "text": ""}


def quote_requirement(topic: str, doc_id: str | None = None) -> dict[str, Any]:
    result = search_pdf(topic, doc_id=doc_id)
    if result.get("error"):
        return result
    results = result.get("results", [])
    if not results:
        return {
            "topic": topic,
            "quote": None,
            "page": None,
            "message": "No matching requirement found in PDF. Do not invent constraints.",
        }
    best = results[0]
    return {
        "topic": topic,
        "quote": best["text"],
        "page": best["page"],
        "citation_required": True,
    }


def read_workspace_file(path: str) -> dict[str, Any]:
    try:
        target = _resolve_workspace_path(path)
        if not target.exists():
            return {"path": path, "error": "File not found", "content": ""}
        if not target.is_file():
            return {"path": path, "error": "Not a file", "content": ""}
        content = target.read_text(encoding="utf-8", errors="replace")
        return {"path": path, "content": content, "lines": len(content.splitlines())}
    except ValueError as e:
        return {"path": path, "error": str(e), "content": ""}


def run_command(cmd: str) -> dict[str, Any]:
    try:
        parts = shlex.split(cmd)
    except ValueError as e:
        return {"cmd": cmd, "error": str(e), "stdout": "", "stderr": "", "exit_code": -1}

    if not parts:
        return {"cmd": cmd, "error": "Empty command", "stdout": "", "stderr": "", "exit_code": -1}

    binary = Path(parts[0]).name
    if binary not in settings.allowed_command_list:
        return {
            "cmd": cmd,
            "error": f"Command '{binary}' not allowed. Allowed: {settings.allowed_command_list}",
            "stdout": "",
            "stderr": "",
            "exit_code": -1,
        }

    parts = _resolve_command(parts)
    workspace = settings.workspace_dir.resolve()
    try:
        proc = subprocess.run(
            parts,
            cwd=str(workspace),
            capture_output=True,
            text=True,
            timeout=settings.run_command_timeout,
            env=_command_env(),
        )
        return {
            "cmd": cmd,
            "stdout": proc.stdout[-4000:] if proc.stdout else "",
            "stderr": proc.stderr[-2000:] if proc.stderr else "",
            "exit_code": proc.returncode,
        }
    except FileNotFoundError:
        return {
            "cmd": cmd,
            "error": f"Command '{binary}' not found. Install it or use python -m pytest.",
            "stdout": "",
            "stderr": "",
            "exit_code": -1,
        }
    except subprocess.TimeoutExpired:
        return {
            "cmd": cmd,
            "error": f"Timed out after {settings.run_command_timeout}s",
            "stdout": "",
            "stderr": "",
            "exit_code": -1,
        }


def summarize_pdf(doc_id: str | None = None) -> dict[str, Any]:
    """Return every page of the uploaded PDF for walkthrough / summary questions."""
    doc_id = doc_id or _current_doc_id
    if not doc_id:
        return {"error": "No document loaded. Upload a PDF first.", "sections": []}

    pages = load_pages_cache(doc_id)
    if not pages:
        return {"error": "PDF pages not cached.", "sections": []}

    sections: list[dict[str, Any]] = []
    for p in pages:
        text = (p.get("text") or "").strip()
        title_match = re.search(r"Page\s+\d+\s*-\s*([^\n=]+)", text, re.I)
        title = title_match.group(1).strip() if title_match else f"Section on page {p['page']}"
        sections.append({"page": p["page"], "title": title, "text": text})

    return {"doc_id": doc_id, "total_pages": len(sections), "sections": sections}


def propose_patch(path: str, explanation: str, new_content: str) -> dict[str, Any]:
    try:
        target = _resolve_workspace_path(path)
        old = target.read_text(encoding="utf-8", errors="replace") if target.exists() else ""
        diff = list(
            difflib.unified_diff(
                old.splitlines(keepends=True),
                new_content.splitlines(keepends=True),
                fromfile=f"a/{path}",
                tofile=f"b/{path}",
            )
        )
        return {"path": path, "explanation": explanation, "diff": "".join(diff), "applied": False}
    except ValueError as e:
        return {"path": path, "error": str(e), "diff": "", "applied": False}


TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "search_pdf",
            "description": "Search the uploaded assignment PDF. Always use before answering PDF-related questions.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_page",
            "description": "Get full text of a PDF page (1-indexed).",
            "parameters": {
                "type": "object",
                "properties": {"page_n": {"type": "integer"}},
                "required": ["page_n"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "quote_requirement",
            "description": "Get a must-cite snippet from the assignment for a topic.",
            "parameters": {
                "type": "object",
                "properties": {"topic": {"type": "string"}},
                "required": ["topic"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "summarize_pdf",
            "description": "Get ALL pages of the uploaded assignment PDF. Use for overview, summary, walkthrough, or 'explain the whole PDF' questions.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_workspace_file",
            "description": "Read a file from the student workspace.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": "Run pytest or python in the sandboxed workspace.",
            "parameters": {
                "type": "object",
                "properties": {"cmd": {"type": "string"}},
                "required": ["cmd"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propose_patch",
            "description": "Suggest a code fix as a diff (does not auto-apply).",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "explanation": {"type": "string"},
                    "new_content": {"type": "string"},
                },
                "required": ["path", "explanation", "new_content"],
            },
        },
    },
]

TOOL_HANDLERS: dict[str, Callable[..., dict[str, Any]]] = {
    "search_pdf": search_pdf,
    "get_page": get_page,
    "quote_requirement": quote_requirement,
    "summarize_pdf": summarize_pdf,
    "read_workspace_file": read_workspace_file,
    "run_command": run_command,
    "propose_patch": propose_patch,
}


def execute_tool(name: str, arguments: dict[str, Any]) -> tuple[str, list[Citation]]:
    handler = TOOL_HANDLERS.get(name)
    if not handler:
        return json.dumps({"error": f"Unknown tool: {name}"}), []

    result = handler(**arguments)
    citations: list[Citation] = []

    if name == "search_pdf":
        for r in result.get("results", []):
            citations.append(Citation(page=r["page"], text=r["text"]))
    elif name == "quote_requirement" and result.get("page") and result.get("quote"):
        citations.append(Citation(page=result["page"], text=result["quote"]))
    elif name == "get_page" and result.get("page") and result.get("text"):
        citations.append(Citation(page=result["page"], text=result["text"][:300]))
    elif name == "summarize_pdf":
        for s in result.get("sections", []):
            if s.get("text"):
                citations.append(Citation(page=s["page"], text=s["text"][:400]))

    return json.dumps(result, ensure_ascii=False), citations
