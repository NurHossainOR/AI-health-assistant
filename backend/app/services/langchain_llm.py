from __future__ import annotations

import base64
import json
import logging
from functools import lru_cache
from typing import Any, AsyncIterator, Optional

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_google_genai import ChatGoogleGenerativeAI

from app.core.config import get_settings
from app.core.exceptions import AppError

logger = logging.getLogger(__name__)

DOCUMENT_EXTRACT_PROMPT = """You are an expert medical document extractor. Extract data from one patient's medical document.
Return JSON only with this shape (fields first so values survive if output is cut off):
{
  "fields": [
    {
      "field_type": "lab" | "medication" | "imaging" | "finding" | "other",
      "name": "test or field name",
      "value": "value as written",
      "unit": "unit or null",
      "reference_low": "low reference or null",
      "reference_high": "high reference or null",
      "observed_at": "YYYY-MM-DD or null",
      "canonical_code": null
    }
  ],
  "document_text": "compact transcription"
}
Rules:
- Put every lab, medication, imaging finding, patient name, sex, age, and report date into fields.
- Keep document_text under 3500 characters: identifiers, date, test names, values, units, reference ranges. Skip letterhead and contact details.
- Do not invent values. Do not diagnose. Do not recommend treatment.
- If a field is unreadable, omit it.
"""


def _require_gemini() -> Any:
    settings = get_settings()
    if not settings.gemini_api_key:
        raise AppError(
            "Chat is not configured. Set GEMINI_API_KEY on the server.",
            status_code=503,
            code="gemini_unconfigured",
        )
    return settings


@lru_cache
def get_chat_llm(temperature: float = 0.2) -> ChatGoogleGenerativeAI:
    settings = _require_gemini()
    return ChatGoogleGenerativeAI(
        model=settings.gemini_chat_model,
        google_api_key=settings.gemini_api_key,
        temperature=temperature,
        max_output_tokens=8192,
    )


@lru_cache
def get_extract_llm() -> ChatGoogleGenerativeAI:
    """Extraction must not spend the output budget on thinking tokens."""
    settings = _require_gemini()
    return ChatGoogleGenerativeAI(
        model=settings.gemini_chat_model,
        google_api_key=settings.gemini_api_key,
        temperature=0.0,
        max_output_tokens=8192,
        thinking_budget=0,
        include_thoughts=False,
        response_mime_type="application/json",
    )


def message_text(message: Any) -> str:
    content = getattr(message, "content", message)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and item.get("text") and not item.get("thought"):
                parts.append(str(item["text"]))
        return "".join(parts)
    return str(content or "")


def _repair_truncated_json(raw: str) -> Optional[dict[str, Any]]:
    start = raw.find("{")
    if start < 0:
        return None
    s = raw[start:]
    in_str = False
    escape = False
    stack: list[str] = []
    for ch in s:
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            stack.append("}")
        elif ch == "[":
            stack.append("]")
        elif ch in "}]":
            if stack:
                stack.pop()
    if in_str:
        s += '"'
    s = s.rstrip()
    if s.endswith(","):
        s = s[:-1]
    s += "".join(reversed(stack))
    try:
        parsed = json.loads(s)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def parse_llm_json(text: str) -> Optional[dict[str, Any]]:
    raw = (text or "").strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        start, end = raw.find("{"), raw.rfind("}")
        parsed = None
        if start >= 0 and end > start:
            try:
                parsed = json.loads(raw[start : end + 1])
            except json.JSONDecodeError:
                parsed = None
        if not isinstance(parsed, dict):
            parsed = _repair_truncated_json(raw)
    return parsed if isinstance(parsed, dict) else None


async def generate_json(
    prompt: str,
    *,
    system: str = "Respond with JSON only. No markdown.",
    temperature: float = 0.0,
) -> Optional[dict[str, Any]]:
    try:
        llm = get_chat_llm(temperature=temperature)
        result = await llm.ainvoke(
            [
                SystemMessage(content=system),
                HumanMessage(content=prompt),
            ]
        )
        return parse_llm_json(message_text(result))
    except Exception as exc:  # noqa: BLE001
        logger.warning("LangChain JSON generation skipped: %s", type(exc).__name__)
        return None


async def classify_json(prompt: str) -> Optional[dict[str, Any]]:
    return await generate_json(prompt)


def _media_parts(mime_type: str, data: bytes, extra_text: str) -> list[dict[str, Any]]:
    parts: list[dict[str, Any]] = [{"type": "text", "text": DOCUMENT_EXTRACT_PROMPT}]
    if extra_text.strip():
        parts.append(
            {
                "type": "text",
                "text": f"Text already extracted from the file (may be incomplete):\n{extra_text[:20000]}",
            }
        )
    b64 = base64.b64encode(data).decode("ascii")
    mime = (mime_type or "application/octet-stream").lower()
    if mime in {"image/jpg", "image/pjpeg"}:
        mime = "image/jpeg"
    if mime.startswith("image/"):
        parts.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}})
    else:
        parts.append({"type": "media", "mime_type": mime, "data": b64})
    return parts


def _finish_reason(message: Any) -> str:
    meta = getattr(message, "response_metadata", None) or {}
    return str(meta.get("finish_reason") or meta.get("finishReason") or "")


async def extract_document_json(
    *,
    mime_type: str,
    data: bytes,
    extra_text: str = "",
) -> Optional[dict[str, Any]]:
    if not data and not extra_text.strip():
        return None
    try:
        llm = get_extract_llm()
        content: Any
        if data:
            content = _media_parts(mime_type, data, extra_text)
        else:
            content = DOCUMENT_EXTRACT_PROMPT + f"\n\nDocument text:\n{extra_text[:20000]}"
        result = await llm.ainvoke(
            [
                SystemMessage(content="Respond with JSON only. No markdown."),
                HumanMessage(content=content),
            ]
        )
        text = message_text(result)
        parsed = parse_llm_json(text)
        if not parsed:
            logger.warning(
                "Document extraction returned non-JSON (finish=%s, chars=%s)",
                _finish_reason(result) or "unknown",
                len(text),
            )
        elif _finish_reason(result) == "MAX_TOKENS":
            logger.warning(
                "Document extraction hit MAX_TOKENS; kept %s fields",
                len(parsed.get("fields") or []) if isinstance(parsed.get("fields"), list) else 0,
            )
        return parsed
    except Exception as exc:  # noqa: BLE001
        logger.warning("Gemini document extraction failed: %s", exc)
        return None


def grounded_chain(system_prompt: str):
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", system_prompt),
            MessagesPlaceholder("history"),
            ("human", "Retrieved context:\n{context}\n\nPatient question: {query}"),
        ]
    )
    return prompt | get_chat_llm(temperature=0.2)


def history_to_messages(rows: list[tuple[str, str]]) -> list[BaseMessage]:
    messages: list[BaseMessage] = []
    for role, content in rows:
        if role == "user":
            messages.append(HumanMessage(content=content))
        else:
            messages.append(AIMessage(content=content))
    return messages


async def stream_grounded_answer(
    *,
    system_prompt: str,
    context: str,
    query: str,
    history: list[tuple[str, str]],
) -> AsyncIterator[str]:
    chain = grounded_chain(system_prompt)
    async for chunk in chain.astream(
        {
            "context": context,
            "query": query,
            "history": history_to_messages(history),
        }
    ):
        text = message_text(chunk)
        if text:
            yield text
