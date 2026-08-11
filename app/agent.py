"""NVIDIA Llama agent with tool calling and session memory."""

from __future__ import annotations

import json
import re
from typing import Any

import httpx
from openai import OpenAI

from app.config import settings
from app.models import ChatResponse, Citation, Message, Session, ToolCallRecord
from app.tools import (
    TOOL_DEFINITIONS,
    execute_tool,
    get_current_doc,
    get_page,
    set_current_doc,
    summarize_pdf,
)

SYSTEM_PROMPT = """You are a friendly coding tutor helping a student with THEIR uploaded assignment PDF and THEIR workspace code.

Rules:
- ALWAYS use tools before answering PDF questions. Never say "I couldn't find" without calling search_pdf, get_page, or summarize_pdf first.
- For overview / summary / "explain the whole PDF" / "detailed walkthrough" questions: call summarize_pdf, then give a page-by-page breakdown synced to page numbers.
- For specific topics (constraints, starter structure, input format): call search_pdf AND get_page for the best matching page.
- EVERY PDF answer must name the PDF page number and file name (e.g. main.py) when relevant.
- NEVER mention tool names, function names, or code syntax like search_pdf() to the student. Speak naturally.
- For code errors: use read_workspace_file and run_command. For fixes: use propose_patch (diff only, not auto-applied).
- LANGUAGE (strict): Follow the language instruction for this message.
- EXPLAIN directly in your reply: summarize what the PDF says in plain language (3-6 sentences). Do NOT tell the student to "check the Answer tab" or "see Code tab" — you must explain yourself. Tabs are extra reference.
- Do not invent requirements not in the PDF."""

_PAGE_REQUEST_RE = re.compile(
    r"\b(?:page\s+(one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|\d+)"
    r"|(?:explain|describe|tell me about)\s+(?:the\s+)?(first|second|third|fourth|fifth)\s+page)\b",
    re.I,
)

_PAGE_WORDS: dict[str, int] = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
    "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5,
}

_OVERVIEW_RE = re.compile(
    r"\b(whole pdf|entire pdf|full pdf|complete pdf|detailed explanation|detailed summary|detailed description|"
    r"cover everything|go through|walkthrough|walk through|overview|summary of|what is in the pdf|what's in the pdf|"
    r"everything in|explain the pdf|pdf content|all pages|page by page|pin to pin|full period|whole period|"
    r"give me a summary|tell me everything)\b",
    re.I,
)

_TOOL_LEAK_RE = re.compile(
    r"`?(search_pdf|get_page|quote_requirement|read_workspace_file|run_command|propose_patch|summarize_pdf)`?"
    r"(?:\([^)]*\))?|\b(call|using|use)\s+(search_pdf|get_page|summarize_pdf)\b",
    re.I,
)

_sessions: dict[str, Session] = {}

_HINGLISH_MARKERS = re.compile(
    r"[\u0900-\u097F]|"
    r"\b(kya|hai|hain|karo|karna|chahiye|hona|hon[ae]|mein|nahi|nahin|"
    r"kaise|kahan|kaha|yeh|woh|aap|tum|mera|apna|wala|wali|"
    r"samjha|samjhao|batao|bata|likho|likhna|chahie|hogi|hoga|karna|krna)\b",
    re.I,
)

_HINGLISH_OUTPUT = re.compile(
    r"[\u0900-\u097F]|"
    r"\b(hai|hain|pe likha|ke hisaab|karna|chahiye|mein|nahi|aapko|humko|"
    r"jismein|humein|banana hai|likhna hai|dekho|samjho|bhai)\b",
    re.I,
)


def get_session(session_id: str | None) -> Session:
    if session_id and session_id in _sessions:
        return _sessions[session_id]
    session = Session(doc_id=get_current_doc())
    _sessions[session.id] = session
    return session


def bind_session_doc(session: Session, doc_id: str | None) -> None:
    session.doc_id = doc_id
    set_current_doc(doc_id)


def _is_hinglish(user_message: str) -> bool:
    return bool(_HINGLISH_MARKERS.search(user_message))


def _looks_hinglish(text: str) -> bool:
    return bool(_HINGLISH_OUTPUT.search(text))


def _reply_language(user_message: str) -> str:
    return "hinglish" if _is_hinglish(user_message) else "english"


def _language_instruction(user_message: str) -> str:
    if _reply_language(user_message) == "hinglish":
        return (
            "Language: Reply in Hinglish (Roman script Hindi-English mix). "
            "Always say 'page X pe' with the exact page number. Name files like main.py explicitly."
        )
    return (
        "Language: Reply in ENGLISH ONLY for this message. "
        "Do NOT use Hindi, Hinglish, or phrases like 'pe likha hai'. "
        "Say 'on page X' instead. Name files explicitly."
    )


def _tag_user_message(text: str, user_message: str) -> str:
    if _reply_language(user_message) == "english":
        return f"[Respond in English only — no Hindi/Hinglish.]\n{text}"
    return f"[Respond in Hinglish — Roman Hindi-English mix.]\n{text}"


def _extract_requested_page(user_message: str) -> int | None:
    m = _PAGE_REQUEST_RE.search(user_message)
    if not m:
        return None
    token = m.group(1).lower()
    if token.isdigit():
        return int(token)
    return _PAGE_WORDS.get(token)


def _explain_from_citation(citation: Citation, user_message: str, llm_reply: str = "") -> str:
    """Build a direct explanation for the chat bubble."""
    hinglish = _is_hinglish(user_message)
    page = citation.page
    file_hint = _extract_file_hint(citation.text)
    section = _extract_section_title(citation.text)
    excerpt = re.sub(r"\s+", " ", citation.text).strip()

    tab_boilerplate = ("answer tab", "code tab", "cites tab", "breakdown", "dekho.", "see page")
    if llm_reply and len(llm_reply) > 50:
        lower = llm_reply.lower()
        if not any(p in lower for p in tab_boilerplate):
            if hinglish or not _looks_hinglish(llm_reply):
                return _summarize_for_speech(llm_reply, 500)

    body = _summarize_for_speech(excerpt, 420)
    title = section or f"page {page}"

    if hinglish:
        msg = f"Page {page} ({title}) pe yeh likha hai: {body}"
        if file_hint:
            msg += f" Yeh `{file_hint}` file se related hai."
        return msg

    msg = f"On page {page} ({title}), the assignment says: {body}"
    if file_hint:
        msg += f" This relates to the `{file_hint}` file."
    return msg


def _build_single_page_response(
    session: Session,
    page_data: dict[str, Any],
    user_message: str,
) -> ChatResponse:
    page = page_data["page"]
    text = page_data.get("text", "")
    citation = Citation(page=page, text=text)
    title = _section_title_from_text(text, page)
    reply = _explain_from_citation(citation, user_message)
    answer_detail = f"📄 Page {page} — {title}\n\n{text}"
    code_blocks = [f"# PDF page {page}\n{text}"] if text else []
    tool_calls = [
        ToolCallRecord(
            name="get_page",
            arguments={"page_n": page},
            result=json.dumps(page_data, ensure_ascii=False)[:2000],
        )
    ]

    session.messages.append(
        Message(role="assistant", text=reply, citations=[citation], tool_calls=tool_calls)
    )
    return ChatResponse(
        session_id=session.id,
        reply=reply,
        answer_detail=answer_detail,
        citations=[citation],
        tool_calls=tool_calls,
        code_blocks=code_blocks,
    )


def _sanitize_reply(text: str) -> str:
    cleaned = _TOOL_LEAK_RE.sub("", text)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
    cleaned = re.sub(r"\.\s*\.", ".", cleaned)
    return cleaned


def _section_title_from_text(text: str, page: int) -> str:
    match = re.search(r"Page\s+\d+\s*-\s*([^\n=]+)", text, re.I)
    return match.group(1).strip() if match else f"Page {page}"


def _build_overview_response(
    session: Session,
    overview: dict[str, Any],
    user_message: str,
    all_tool_calls: list[ToolCallRecord],
) -> ChatResponse:
    sections = overview.get("sections", [])
    hinglish = _is_hinglish(user_message)
    citations = [Citation(page=s["page"], text=s["text"]) for s in sections if s.get("text")]
    code_blocks = [f"# PDF page {s['page']} — {s['title']}\n{s['text']}" for s in sections]

    lines: list[str] = []
    if hinglish:
        lines.append(f"📚 Poora assignment PDF — {len(sections)} pages (page-by-page):")
    else:
        lines.append(f"📚 Full assignment PDF — {len(sections)} pages (page-by-page):")

    for s in sections:
        lines.append("")
        lines.append(f"📄 Page {s['page']} — {s['title']}")
        preview = s["text"].replace("\n", " ").strip()
        if len(preview) > 320:
            preview = preview[:319].rsplit(" ", 1)[0] + "…"
        lines.append(preview)

    answer_detail = "\n".join(lines)

    first = sections[0] if sections else None
    if hinglish:
        speech = f"PDF mein {len(sections)} pages hain. "
        if first:
            speech += f"Page 1: {_summarize_for_speech(first['text'], 200)} "
        for s in sections[1:3]:
            speech += f"Page {s['page']}: {_summarize_for_speech(s['text'], 120)} "
    else:
        speech = f"Your PDF has {len(sections)} pages. "
        if first:
            speech += f"Page 1: {_summarize_for_speech(first['text'], 200)} "
        for s in sections[1:3]:
            speech += f"Page {s['page']}: {_summarize_for_speech(s['text'], 120)} "
    speech = _summarize_for_speech(speech.strip(), 900)

    all_tool_calls.append(
        ToolCallRecord(name="summarize_pdf", arguments={}, result=json.dumps(overview, ensure_ascii=False)[:2000])
    )

    session.messages.append(
        Message(role="assistant", text=speech, citations=citations, tool_calls=all_tool_calls)
    )

    return ChatResponse(
        session_id=session.id,
        reply=speech,
        answer_detail=answer_detail,
        citations=citations,
        tool_calls=all_tool_calls,
        code_blocks=code_blocks,
    )


def _extract_code_blocks(text: str) -> tuple[str, list[str]]:
    pattern = re.compile(r"```(?:[\w]*)?\n?(.*?)```", re.DOTALL)
    blocks = [b.strip() for b in pattern.findall(text) if b.strip()]
    spoken = pattern.sub("", text).strip()
    if not spoken:
        spoken = "[see code panel]" if blocks else ""
    return spoken, blocks


def _extract_file_hint(text: str) -> str | None:
    match = re.search(r"\b[\w./-]+\.py\b", text)
    return match.group(0) if match else None


def _extract_section_title(text: str) -> str | None:
    match = re.search(r"Page\s+\d+\s*-\s*([^\n=]+)", text, re.I)
    return match.group(1).strip() if match else None


def _summarize_for_speech(text: str, max_len: int = 120) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    if len(cleaned) <= max_len:
        return cleaned
    return cleaned[: max_len - 1].rsplit(" ", 1)[0] + "…"


def _code_blocks_from_tools(tool_calls: list[ToolCallRecord]) -> list[str]:
    blocks: list[str] = []
    for tc in tool_calls:
        try:
            result = json.loads(tc.result)
        except json.JSONDecodeError:
            continue
        if tc.name == "propose_patch" and result.get("diff"):
            header = f"# {result.get('path', 'patch')}"
            if result.get("explanation"):
                header += f"\n# {result['explanation']}"
            blocks.append(f"{header}\n{result['diff']}")
        elif tc.name == "read_workspace_file" and result.get("content"):
            path = result.get("path", "file")
            blocks.append(f"# workspace/{path}\n{result['content']}")
        elif tc.name in {"get_page", "quote_requirement"} and result.get("text"):
            page = result.get("page", "?")
            blocks.append(f"# PDF page {page}\n{result['text'].strip()}")
        elif tc.name == "summarize_pdf":
            for s in result.get("sections", []):
                if s.get("text"):
                    blocks.append(f"# PDF page {s['page']} — {s.get('title', 'section')}\n{s['text']}")
        elif tc.name == "search_pdf":
            for hit in result.get("results", [])[:2]:
                page = hit.get("page", "?")
                text = hit.get("text", "").strip()
                if text and ("class " in text or "def " in text or ".py" in text or "Structure" in text):
                    blocks.append(f"# PDF page {page} (search hit)\n{text}")
    return blocks


def _code_blocks_from_citations(citations: list[Citation]) -> list[str]:
    blocks: list[str] = []
    for c in citations[:3]:
        text = c.text.strip()
        if not text:
            continue
        if any(k in text for k in ("class ", "def ", ".py", "Structure", "TODO", "Input Format", "Constraints")):
            blocks.append(f"# PDF page {c.page}\n{text}")
    return blocks


def _build_answer_detail(
    llm_reply: str,
    citations: list[Citation],
    code_blocks: list[str],
    user_message: str,
) -> str:
    if not citations:
        if _reply_language(user_message) == "english" and _looks_hinglish(llm_reply):
            return "See the Answer tab for details from your PDF."
        return llm_reply

    hinglish = _is_hinglish(user_message)
    primary = citations[0]
    page = primary.page
    section = _extract_section_title(primary.text)
    file_hint = _extract_file_hint(primary.text)
    all_pages = sorted({c.page for c in citations})

    lines: list[str] = []
    if hinglish:
        title = section or "Assignment detail"
        lines.append(f"📄 Page {page} — {title}")
        lines.append("")
        if file_hint:
            lines.append(f"Kahan: `{file_hint}` file — workspace folder mein banao/edit karo.")
        else:
            lines.append("Kahan: Assignment PDF (neeche exact text dekho).")
        lines.append("")
        lines.append("Kya likha hai (PDF se):")
        lines.append(_summarize_for_speech(primary.text, 280))
        lines.append("")
        if len(all_pages) > 1:
            others = ", ".join(f"page {p}" for p in all_pages if p != page)
            lines.append(f"Aur related pages: {others} — Cites tab mein.")
        if code_blocks:
            lines.append("Code / structure: Code tab ↑ dekho.")
        if llm_reply and llm_reply not in ("[see code panel]", ""):
            if hinglish or not _looks_hinglish(llm_reply):
                lines.append("")
                lines.append("Explanation:")
                lines.append(llm_reply)
    else:
        title = section or "Assignment detail"
        lines.append(f"📄 Page {page} — {title}")
        lines.append("")
        if file_hint:
            lines.append(f"Where: Create/edit `{file_hint}` in the workspace folder.")
        else:
            lines.append("Where: See your assignment PDF (exact excerpt below).")
        lines.append("")
        lines.append("What the PDF says:")
        lines.append(_summarize_for_speech(primary.text, 280))
        lines.append("")
        if len(all_pages) > 1:
            others = ", ".join(f"page {p}" for p in all_pages if p != page)
            lines.append(f"Related pages: {others} — see Cites tab.")
        if code_blocks:
            lines.append("Code / structure: see Code tab ↑.")
        if llm_reply and llm_reply not in ("[see code panel]", ""):
            if hinglish or not _looks_hinglish(llm_reply):
                lines.append("")
                lines.append("Explanation:")
                lines.append(llm_reply)

    return "\n".join(lines)


    return "\n".join(lines)


def _wants_pdf_overview(user_message: str) -> bool:
    if not _OVERVIEW_RE.search(user_message):
        return False
    vague = re.search(r"\b(what is that|what's that|explain that|tell me more)\b", user_message, re.I)
    mentions_pdf = re.search(r"\bpdf\b|\bassignment\b|\bdocument\b|\bpages?\b", user_message, re.I)
    if vague and not mentions_pdf:
        return False
    return True


def _nvidia_client() -> OpenAI:
    return OpenAI(
        api_key=settings.nvidia_api_key,
        base_url=settings.nvidia_base_url,
        http_client=httpx.Client(trust_env=False),
    )


def chat(session_id: str | None, user_message: str, doc_id: str | None = None) -> ChatResponse:
    session = get_session(session_id)
    if doc_id:
        bind_session_doc(session, doc_id)
    elif session.doc_id:
        set_current_doc(session.doc_id)

    session.messages.append(Message(role="user", text=user_message))

    active_doc = doc_id or session.doc_id or get_current_doc()

    page_n = _extract_requested_page(user_message)
    if active_doc and page_n:
        set_current_doc(active_doc)
        page_data = get_page(page_n, active_doc)
        if page_data.get("text"):
            return _build_single_page_response(session, page_data, user_message)

    if _wants_pdf_overview(user_message) and active_doc:
        set_current_doc(active_doc)
        overview = summarize_pdf(active_doc)
        if overview.get("sections"):
            return _build_overview_response(session, overview, user_message, [])

    client = _nvidia_client()
    all_citations: list[Citation] = []
    all_tool_calls: list[ToolCallRecord] = []

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "system", "content": _language_instruction(user_message)},
    ]
    for msg in session.messages[-20:]:
        content = msg.text
        if msg.role == "user" and msg is session.messages[-1]:
            content = _tag_user_message(msg.text, user_message)
        messages.append({"role": msg.role, "content": content})

    final_reply = ""
    for _ in range(6):
        response = client.chat.completions.create(
            model=settings.nvidia_llm_model,
            messages=messages,
            tools=TOOL_DEFINITIONS,
            tool_choice="auto",
            temperature=0.2,
            top_p=0.7,
            max_tokens=1024,
        )
        assistant_msg = response.choices[0].message

        if assistant_msg.tool_calls:
            messages.append(assistant_msg.model_dump(exclude_none=True))
            for tc in assistant_msg.tool_calls:
                args = json.loads(tc.function.arguments)
                result_str, cites = execute_tool(tc.function.name, args)
                all_citations.extend(cites)
                all_tool_calls.append(
                    ToolCallRecord(name=tc.function.name, arguments=args, result=result_str[:2000])
                )
                messages.append({"role": "tool", "tool_call_id": tc.id, "content": result_str})
            continue

        final_reply = assistant_msg.content or ""
        break

    final_reply = _sanitize_reply(final_reply)

    if not final_reply:
        if _reply_language(user_message) == "english":
            final_reply = "Sorry, I couldn't generate an answer. Please try again."
        else:
            final_reply = "Sorry, main answer generate nahi kar paya. Please try again."

    spoken, code_blocks = _extract_code_blocks(final_reply)
    code_blocks.extend(_code_blocks_from_tools(all_tool_calls))
    code_blocks.extend(_code_blocks_from_citations(all_citations))

    seen: set[str] = set()
    unique_blocks: list[str] = []
    for block in code_blocks:
        key = block.strip()
        if key and key not in seen:
            seen.add(key)
            unique_blocks.append(block)
    code_blocks = unique_blocks

    seen_pages: set[int] = set()
    unique_citations: list[Citation] = []
    for c in all_citations:
        if c.page not in seen_pages:
            seen_pages.add(c.page)
            unique_citations.append(c)

    if not unique_citations and active_doc:
        result_str, cites = execute_tool("search_pdf", {"query": user_message[:200]})
        if cites:
            all_tool_calls.append(
                ToolCallRecord(name="search_pdf", arguments={"query": user_message[:200]}, result=result_str[:2000])
            )
            unique_citations = cites
            code_blocks.extend(_code_blocks_from_citations(cites))

    answer_detail = _build_answer_detail(spoken, unique_citations, code_blocks, user_message)
    if unique_citations:
        reply = _explain_from_citation(unique_citations[0], user_message, spoken)
    elif spoken and spoken not in ("[see code panel]", ""):
        reply = _summarize_for_speech(spoken, 500)
    else:
        reply = (
            "PDF mein yeh detail nahi mili."
            if _is_hinglish(user_message)
            else "I couldn't find that in your PDF."
        )

    session.messages.append(
        Message(role="assistant", text=reply, citations=all_citations, tool_calls=all_tool_calls)
    )

    return ChatResponse(
        session_id=session.id,
        reply=reply,
        answer_detail=answer_detail,
        citations=unique_citations,
        tool_calls=all_tool_calls,
        code_blocks=code_blocks,
    )
