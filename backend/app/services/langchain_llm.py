from __future__ import annotations

import base64
import json
import logging
import time
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, AsyncIterator, Optional

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI

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


class LLMUnavailable(Exception):
    """Every configured model failed or is cooling down."""


# Provider/model → monotonic time until which it is skipped (quota or rate limit hit).
_cooldowns: dict[str, float] = {}
QUOTA_COOLDOWN_SECONDS = 15 * 60
RATE_LIMIT_COOLDOWN_SECONDS = 60


@dataclass(frozen=True)
class Candidate:
    name: str  # e.g. "gemini:gemini-3-flash-preview", "openrouter:qwen/qwen3.8-27b:free"
    llm: BaseChatModel
    provider: str  # gemini | openrouter


def llm_configured() -> bool:
    settings = get_settings()
    return bool(settings.gemini_api_key or settings.openrouter_api_key)


def _require_llm() -> Any:
    settings = get_settings()
    if not llm_configured():
        raise AppError(
            "Chat is not configured. Set GEMINI_API_KEY or OPENROUTER_API_KEY on the server.",
            status_code=503,
            code="llm_unconfigured",
        )
    return settings


def _is_quota_error(exc: BaseException) -> bool:
    text = f"{type(exc).__name__} {exc}".lower()
    return "resourceexhausted" in text or "quota" in text


def _is_rate_limit(exc: BaseException) -> bool:
    text = f"{type(exc).__name__} {exc}".lower()
    return "429" in text or "ratelimit" in text or "rate-limit" in text or "rate limit" in text


def _cooling_down(name: str) -> bool:
    until = _cooldowns.get(name)
    return until is not None and until > time.monotonic()


def _record_failure(name: str, exc: BaseException) -> None:
    if _is_quota_error(exc):
        _cooldowns[name] = time.monotonic() + QUOTA_COOLDOWN_SECONDS
    elif _is_rate_limit(exc):
        _cooldowns[name] = time.monotonic() + RATE_LIMIT_COOLDOWN_SECONDS
    logger.warning("LLM %s failed (%s); trying next model", name, type(exc).__name__)


@lru_cache
def _gemini_llm(temperature: float, json_mode: bool) -> ChatGoogleGenerativeAI:
    settings = get_settings()
    kwargs: dict[str, Any] = {}
    if json_mode:
        # Structured output must not spend the output budget on thinking tokens.
        kwargs.update(
            thinking_budget=0, include_thoughts=False, response_mime_type="application/json"
        )
    return ChatGoogleGenerativeAI(
        model=settings.gemini_chat_model,
        google_api_key=settings.gemini_api_key,
        temperature=temperature,
        max_output_tokens=8192,
        # Fail over quickly instead of retrying a spent quota; fallbacks take over.
        max_retries=1 if settings.openrouter_api_key else 6,
        timeout=settings.llm_timeout_seconds,
        **kwargs,
    )


@lru_cache
def _openrouter_llm(model: str, temperature: float) -> ChatOpenAI:
    settings = get_settings()
    return ChatOpenAI(
        model=model,
        api_key=settings.openrouter_api_key,
        base_url=settings.openrouter_base_url,
        temperature=temperature,
        max_tokens=8192,
        timeout=settings.llm_timeout_seconds,
        max_retries=0,
        default_headers={"HTTP-Referer": settings.frontend_url, "X-Title": "Spondon"},
        # Keep reasoning models' chain-of-thought out of the answer text.
        extra_body={"reasoning": {"exclude": True}},
    )


def candidates(
    *, temperature: float = 0.0, json_mode: bool = False, vision: bool = False
) -> list[Candidate]:
    """Gemini first, then OpenRouter fallbacks, skipping models that are cooling down."""
    settings = _require_llm()
    out: list[Candidate] = []
    if settings.gemini_api_key:
        name = f"gemini:{settings.gemini_chat_model}"
        out.append(Candidate(name, _gemini_llm(temperature, json_mode), "gemini"))
    if settings.openrouter_api_key:
        models = (
            settings.openrouter_vision_model_list if vision else settings.openrouter_text_model_list
        )
        for model in models:
            out.append(
                Candidate(f"openrouter:{model}", _openrouter_llm(model, temperature), "openrouter")
            )
    ready = [c for c in out if not _cooling_down(c.name)]
    # If everything is cooling down, still try them all rather than refusing outright.
    return ready or out


def model_label(candidate: Candidate) -> str:
    return candidate.name.split(":", 1)[1]


async def ainvoke_with_fallback(
    messages_for: Any,
    *,
    temperature: float = 0.0,
    json_mode: bool = False,
    vision: bool = False,
    accept: Any = None,
) -> tuple[Any, Candidate]:
    """Invoke each candidate in order until one succeeds.

    messages_for(candidate) builds provider-specific messages (or returns None to skip it).
    accept(result) may reject a reply (e.g. non-JSON) so the next model is tried.
    """
    last_exc: Optional[BaseException] = None
    for candidate in candidates(temperature=temperature, json_mode=json_mode, vision=vision):
        messages = messages_for(candidate) if callable(messages_for) else messages_for
        if messages is None:
            continue
        try:
            result = await candidate.llm.ainvoke(messages)
        except Exception as exc:  # noqa: BLE001
            _record_failure(candidate.name, exc)
            last_exc = exc
            continue
        if accept is not None and not accept(result):
            logger.warning("LLM %s returned an unusable reply; trying next model", candidate.name)
            continue
        if candidate.provider != "gemini":
            logger.info("LLM request served by fallback %s", candidate.name)
        return result, candidate
    raise LLMUnavailable("All language models failed") from last_exc


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


async def generate_json_with_model(
    prompt: str,
    *,
    system: str = "Respond with JSON only. No markdown.",
    temperature: float = 0.0,
    json_mode: bool = False,
) -> tuple[Optional[dict[str, Any]], Optional[str]]:
    """(parsed JSON, model that produced it). json_mode avoids thinking tokens on Gemini."""
    messages = [SystemMessage(content=system), HumanMessage(content=prompt)]
    try:
        result, candidate = await ainvoke_with_fallback(
            messages,
            temperature=temperature,
            json_mode=json_mode,
            accept=lambda r: parse_llm_json(message_text(r)) is not None,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("LangChain JSON generation skipped: %s", type(exc).__name__)
        return None, None
    return parse_llm_json(message_text(result)), model_label(candidate)


async def generate_json(
    prompt: str,
    *,
    system: str = "Respond with JSON only. No markdown.",
    temperature: float = 0.0,
    json_mode: bool = False,
) -> Optional[dict[str, Any]]:
    parsed, _ = await generate_json_with_model(
        prompt, system=system, temperature=temperature, json_mode=json_mode
    )
    return parsed


async def classify_json(prompt: str) -> Optional[dict[str, Any]]:
    return await generate_json(prompt)


def _media_parts(
    mime_type: str, data: bytes, extra_text: str, *, provider: str = "gemini"
) -> Optional[list[dict[str, Any]]]:
    """Gemini takes PDFs/images inline; OpenAI-compatible fallbacks only take images.

    Returns None when this provider can't read the file and there is no extracted text.
    """
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
    elif provider == "gemini":
        parts.append({"type": "media", "mime_type": mime, "data": b64})
    elif not extra_text.strip():
        return None
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
    is_image = (mime_type or "").lower().startswith("image/")

    def messages_for(candidate: Candidate):
        content: Any
        if data:
            content = _media_parts(mime_type, data, extra_text, provider=candidate.provider)
            if content is None:
                return None
        else:
            content = DOCUMENT_EXTRACT_PROMPT + f"\n\nDocument text:\n{extra_text[:20000]}"
        return [
            SystemMessage(content="Respond with JSON only. No markdown."),
            HumanMessage(content=content),
        ]

    try:
        result, candidate = await ainvoke_with_fallback(
            messages_for,
            json_mode=True,
            vision=bool(data) and is_image,
            accept=lambda r: parse_llm_json(message_text(r)) is not None,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Document extraction failed on every model: %s", exc)
        return None
    text = message_text(result)
    parsed = parse_llm_json(text)
    if _finish_reason(result) in {"MAX_TOKENS", "length"} and parsed:
        logger.warning(
            "Document extraction by %s hit the token limit; kept %s fields",
            candidate.name,
            len(parsed.get("fields") or []) if isinstance(parsed.get("fields"), list) else 0,
        )
    return parsed


def grounded_prompt(system_prompt: str) -> ChatPromptTemplate:
    return ChatPromptTemplate.from_messages(
        [
            ("system", system_prompt),
            MessagesPlaceholder("history"),
            ("human", "Retrieved context:\n{context}\n\nPatient question: {query}"),
        ]
    )


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
    """Stream from the first model that starts answering.

    A model that fails before its first token is skipped; once tokens have been sent to the
    client a mid-stream failure is raised, since the partial answer can't be taken back.
    """
    messages = grounded_prompt(system_prompt).format_messages(
        context=context, query=query, history=history_to_messages(history)
    )
    last_exc: Optional[BaseException] = None
    for candidate in candidates(temperature=0.2):
        started = False
        try:
            async for chunk in candidate.llm.astream(messages):
                text = message_text(chunk)
                if text:
                    started = True
                    yield text
            if started:
                return
            logger.warning("LLM %s streamed an empty answer; trying next model", candidate.name)
        except Exception as exc:  # noqa: BLE001
            if started:
                raise
            _record_failure(candidate.name, exc)
            last_exc = exc
    raise LLMUnavailable("All language models failed") from last_exc
