from datetime import datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


def new_id() -> str:
    return str(uuid4())


class Document(BaseModel):
    id: str = Field(default_factory=new_id)
    filename: str
    pages: int
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Chunk(BaseModel):
    doc_id: str
    page: int
    text: str
    chunk_index: int


class Citation(BaseModel):
    page: int
    text: str
    score: float | None = None


class ToolCallRecord(BaseModel):
    name: str
    arguments: dict[str, Any]
    result: str


class Message(BaseModel):
    id: str = Field(default_factory=new_id)
    role: Literal["user", "assistant", "system"]
    text: str
    citations: list[Citation] = Field(default_factory=list)
    tool_calls: list[ToolCallRecord] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Session(BaseModel):
    id: str = Field(default_factory=new_id)
    doc_id: str | None = None
    messages: list[Message] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None
    doc_id: str | None = None


class ChatResponse(BaseModel):
    session_id: str
    reply: str
    answer_detail: str = ""
    citations: list[Citation]
    tool_calls: list[ToolCallRecord]
    code_blocks: list[str] = Field(default_factory=list)


class UploadResponse(BaseModel):
    document: Document
    pages_preview: list[dict[str, Any]]
    suggested_prompts: list[str] = Field(default_factory=list)
