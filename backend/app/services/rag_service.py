from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import AppError
from app.models.chat import ChatMessage, ChatRole, ChatSession
from app.models.document import Document, ExtractedField, ImagingStudy
from app.models.user import User, UserRole
from app.services import embedding_service, langchain_llm, vectorstore
from app.services.audit_service import write_audit_log
from app.services.embedding_service import format_source_date, source_label
from app.services.rag_queries import (
    patient_scoped_imaging_query,
    patient_scoped_structured_query,
)

logger = logging.getLogger(__name__)

INSUFFICIENT_REPLY = "I don't see that in your records"
INSUFFICIENT_REPLY_BN = "আপনার রেকর্ডে আমি এটি দেখতে পাচ্ছি না"
INSUFFICIENT_REPLIES = {"en": INSUFFICIENT_REPLY, "bn": INSUFFICIENT_REPLY_BN}

LANGUAGE_RULES = {
    "bn": (
        "\nLANGUAGE: Write the entire answer in simple, natural Bangla (বাংলা). Keep medical test "
        "names, abbreviations, numbers, units, dates and [Source N] markers exactly as written. "
        f'If the answer is not in the context, reply exactly "{INSUFFICIENT_REPLY_BN}".\n'
    ),
}

GROUNDED_SYSTEM_PROMPT = """You are an expert medical records analyst for one patient. You answer questions using only the retrieved context from that patient's uploaded medical documents.
STRICT RULES:
1. Answer only from the provided context. If the answer isn't in the
   context, say "I don't see that in your records" — never fill gaps
   with general medical knowledge presented as if it's from their data.
2. You may explain what a medical term means in general (clearly
   labeled as general information), but you must never:
   - Suggest a diagnosis
   - Recommend a treatment or medication change
   - Interpret what a combination of findings "means" for the patient's
     health status
   - Speculate about causes of abnormal values
3. Every factual claim about the patient's data must cite its source:
   document type and date (e.g., "per your CBC from March 12, 2026").
   Also append a marker like [Source 1] matching the retrieved context block.
4. If asked something diagnostic ("do I have X", "should I worry about Y"),
   redirect clearly: acknowledge what the records show factually, then
   state this is a question for their doctor.
5. If retrieved context is ambiguous, outdated, or conflicting across
   documents, say so explicitly rather than picking one interpretation.

Do not use information from outside the retrieved context. Do not invent dates, values, or document types.
"""

LAB_ALIASES: dict[str, list[str]] = {
    "cholesterol": ["LDL Cholesterol", "HDL Cholesterol", "Triglycerides"],
    "ldl": ["LDL Cholesterol"],
    "hdl": ["HDL Cholesterol"],
    "triglyceride": ["Triglycerides"],
    "triglycerides": ["Triglycerides"],
    "hemoglobin a1c": ["Hemoglobin A1c"],
    "haemoglobin a1c": ["Hemoglobin A1c"],
    "a1c": ["Hemoglobin A1c"],
    "hba1c": ["Hemoglobin A1c"],
    "haemoglobin": ["Hemoglobin"],
    "hemoglobin": ["Hemoglobin"],
    "glucose": ["Glucose"],
    "sugar": ["Glucose"],
    "cbc": ["WBC", "RBC", "Hemoglobin", "Hematocrit", "Platelet"],
}

STRUCTURED_RE = re.compile(
    r"last\s+\d+|readings?|values?|cholesterol|\bldl\b|\bhdl\b|triglyceride|"
    r"a1c|hba1c|glucose|hemoglobin|medication|prescription|dosage|how much|"
    r"what was my|what were my|lab results?|blood test|\bcbc\b|platelet|"
    r"creatinine|\btsh\b|vitamin",
    re.I,
)
SEMANTIC_RE = re.compile(
    r"\bmri\b|\bct\b|scan|finding|impression|follow-?up|\bdue\b|discharge|"
    r"what did .{0,40} say|report said|imaging|explained?",
    re.I,
)
LIMIT_RE = re.compile(
    r"\blast\s+(\d+|one|two|three|four|five|six|seven|eight|nine|ten)\b",
    re.I,
)
WORD_LIMITS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
}


@dataclass
class Intent:
    intent: str  # structured_lookup | semantic_search | hybrid
    entity_type: str = "any"
    names: list[str] = field(default_factory=list)
    limit: int = 6
    source: str = "heuristic"


@dataclass
class RetrievedChunk:
    chunk_text: str
    document_id: UUID
    patient_id: UUID
    doc_type: str
    source_date: str
    label: str
    distance: Optional[float] = None
    retrieval: str = "vector"
    metadata: dict[str, Any] = field(default_factory=dict)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _expand_names(names: list[str]) -> list[str]:
    expanded: list[str] = []
    for name in names:
        key = name.strip().lower()
        if key in LAB_ALIASES:
            expanded.extend(LAB_ALIASES[key])
        else:
            expanded.append(name.strip())
    return list(dict.fromkeys(n for n in expanded if n))


def classify_intent_heuristic(query: str) -> Intent:
    structured = bool(STRUCTURED_RE.search(query))
    semantic = bool(SEMANTIC_RE.search(query))
    if structured and semantic:
        intent = "hybrid"
    elif structured:
        intent = "structured_lookup"
    else:
        intent = "semantic_search"

    names: list[str] = []
    lowered = query.lower()
    a1c_phrase = any(
        token in lowered
        for token in ("hemoglobin a1c", "haemoglobin a1c", "hba1c")
    )
    for alias, canonical in sorted(LAB_ALIASES.items(), key=lambda item: -len(item[0])):
        if alias not in lowered:
            continue
        if alias in {"hemoglobin", "haemoglobin"} and a1c_phrase:
            continue
        names.extend(canonical)
    if "medication" in lowered or "prescription" in lowered:
        entity_type = "medication"
    elif re.search(r"\bmri\b|\bct\b|scan|imaging", lowered):
        entity_type = "imaging"
    elif names or structured:
        entity_type = "lab"
    else:
        entity_type = "any"

    match = LIMIT_RE.search(query)
    if match:
        raw = match.group(1).lower()
        limit = int(raw) if raw.isdigit() else WORD_LIMITS.get(raw, 6)
    else:
        limit = 6
    return Intent(
        intent=intent,
        entity_type=entity_type,
        names=list(dict.fromkeys(names)),
        limit=max(1, min(limit, 20)),
        source="heuristic",
    )


async def classify_intent(query: str) -> Intent:
    heuristic = classify_intent_heuristic(query)
    if heuristic.intent != "hybrid":
        return heuristic
    prompt = (
        "Classify this patient question about their own medical records. "
        "Return JSON only with keys: intent (structured_lookup|semantic_search|hybrid), "
        "entity_type (lab|medication|imaging|any), names (array of lab/medication names), "
        "limit (integer, default 6).\n"
        "structured_lookup = numeric values, last N readings, medications, dates of tests.\n"
        "semantic_search = findings, what a report said, follow-up due, impressions.\n"
        "hybrid = needs both.\n\n"
        f"Question: {query}"
    )
    parsed = await langchain_llm.classify_json(prompt)
    if not parsed:
        return heuristic
    intent = str(parsed.get("intent") or heuristic.intent)
    if intent not in {"structured_lookup", "semantic_search", "hybrid"}:
        intent = heuristic.intent
    names = parsed.get("names") or heuristic.names
    if not isinstance(names, list):
        names = heuristic.names
    entity = str(parsed.get("entity_type") or heuristic.entity_type)
    if entity not in {"lab", "medication", "imaging", "any"}:
        entity = heuristic.entity_type
    try:
        limit = int(parsed.get("limit") or heuristic.limit)
    except (TypeError, ValueError):
        limit = heuristic.limit
    return Intent(
        intent=intent,
        entity_type=entity,
        names=_expand_names([str(n) for n in names if n] or heuristic.names),
        limit=max(1, min(limit, 20)),
        source="gemini",
    )


def _chunk_from_field(field: ExtractedField, document: Document) -> RetrievedChunk:
    doc_type = document.doc_type.value
    source_date = format_source_date(document.confirmed_at or document.uploaded_at)
    label = source_label(doc_type, source_date)
    observed = f"; observed {field.observed_at}" if field.observed_at else ""
    text = (
        f"{label}. {field.field_type} field '{field.name}'"
        f"{f': {field.value}' if field.value else ''}"
        f"{f' {field.unit}' if field.unit else ''}"
        f"{observed}."
    )
    return RetrievedChunk(
        chunk_text=text,
        document_id=document.id,
        patient_id=document.patient_id,
        doc_type=doc_type,
        source_date=source_date,
        label=label,
        retrieval="sql",
        metadata={"field_name": field.name, "field_type": field.field_type},
    )


def _chunk_from_study(study: ImagingStudy, document: Document) -> RetrievedChunk:
    doc_type = document.doc_type.value
    source_date = format_source_date(document.confirmed_at or document.uploaded_at)
    label = source_label(doc_type, source_date)
    bits = [f"{label}. Imaging study."]
    if study.modality:
        bits.append(f"Modality: {study.modality}.")
    if study.body_part:
        bits.append(f"Body part: {study.body_part}.")
    if study.findings_text:
        bits.append(f"Findings: {study.findings_text}.")
    return RetrievedChunk(
        chunk_text=" ".join(bits),
        document_id=document.id,
        patient_id=document.patient_id,
        doc_type=doc_type,
        source_date=source_date,
        label=label,
        retrieval="sql",
        metadata={"chunk_kind": "imaging"},
    )


def _chunk_from_vector_doc(doc, patient_id: UUID) -> RetrievedChunk | None:
    meta = doc.metadata or {}
    meta_pid = str(meta.get("patient_id") or "")
    if meta_pid != str(patient_id):
        return None
    try:
        document_id = UUID(str(meta.get("document_id")))
    except (TypeError, ValueError):
        return None
    doc_type = str(meta.get("doc_type") or "other")
    source_date = str(meta.get("source_date") or "")
    label = str(meta.get("label") or source_label(doc_type, source_date))
    return RetrievedChunk(
        chunk_text=doc.page_content,
        document_id=document_id,
        patient_id=patient_id,
        doc_type=doc_type,
        source_date=source_date,
        label=label,
        retrieval="vector",
        metadata=meta,
    )


async def retrieve_structured(
    db: AsyncSession,
    patient_id: UUID,
    intent: Intent,
) -> list[RetrievedChunk]:
    chunks: list[RetrievedChunk] = []
    if intent.entity_type in {"any", "lab", "medication"}:
        result = await db.execute(
            patient_scoped_structured_query(
                patient_id,
                names=intent.names,
                entity_type=intent.entity_type if intent.entity_type != "any" else "any",
                limit=max(intent.limit * 3, 12),
            )
        )
        for field, document in result.all():
            chunks.append(_chunk_from_field(field, document))
    if intent.entity_type == "imaging" or (
        intent.intent == "hybrid" and intent.entity_type in {"any", "imaging"}
    ):
        result = await db.execute(patient_scoped_imaging_query(patient_id, limit=12))
        for study, document in result.all():
            chunks.append(_chunk_from_study(study, document))
    if intent.limit:
        chunks = chunks[: intent.limit]
    return chunks


async def retrieve_vector(
    db: AsyncSession,
    patient_id: UUID,
    query: str,
) -> list[RetrievedChunk]:
    settings = get_settings()
    try:
        docs = await vectorstore.asimilarity_search(query, patient_id, k=settings.rag_top_k)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Chroma similarity search failed: %s", exc)
        return []
    chunks: list[RetrievedChunk] = []
    for doc in docs:
        chunk = _chunk_from_vector_doc(doc, patient_id)
        if chunk:
            chunks.append(chunk)
    return chunks


def _dedupe(chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
    seen: set[tuple[UUID, str]] = set()
    unique: list[RetrievedChunk] = []
    for chunk in chunks:
        key = (chunk.document_id, chunk.chunk_text[:160])
        if key in seen:
            continue
        seen.add(key)
        unique.append(chunk)
    return unique


async def retrieve_for_query(
    db: AsyncSession,
    patient_id: UUID,
    query: str,
    intent: Intent,
) -> list[RetrievedChunk]:
    await embedding_service.ensure_patient_indexed(db, patient_id)
    chunks: list[RetrievedChunk] = []
    if intent.intent in {"structured_lookup", "hybrid"}:
        chunks.extend(await retrieve_structured(db, patient_id, intent))
        if intent.intent == "structured_lookup":
            return _dedupe(chunks)[: get_settings().rag_top_k]
    if intent.intent in {"semantic_search", "hybrid"}:
        vector_chunks = await retrieve_vector(db, patient_id, query)
        if intent.intent == "hybrid":
            vector_chunks = [
                chunk
                for chunk in vector_chunks
                if str(chunk.metadata.get("chunk_kind") or "").startswith("text_")
            ]
        chunks.extend(vector_chunks)
    return _dedupe(chunks)[: get_settings().rag_top_k]


def format_context(chunks: list[RetrievedChunk]) -> str:
    if not chunks:
        return "(no matching records)"
    blocks = []
    for i, chunk in enumerate(chunks, start=1):
        blocks.append(
            f"[Source {i}] {chunk.label} (document_id={chunk.document_id})\n{chunk.chunk_text}"
        )
    return "\n\n".join(blocks)


SOURCE_MARK_RE = re.compile(r"\[Source\s+(\d+)\]", re.I)


def citations_from_chunks(chunks: list[RetrievedChunk]) -> list[dict[str, Any]]:
    return [
        {
            "source_index": i,
            "document_id": str(chunk.document_id),
            "doc_type": chunk.doc_type,
            "label": chunk.label,
            "source_date": chunk.source_date,
        }
        for i, chunk in enumerate(chunks, start=1)
    ]


def citations_cited_in_answer(text: str, chunks: list[RetrievedChunk]) -> list[dict[str, Any]]:
    catalog = citations_from_chunks(chunks)
    by_index = {item["source_index"]: item for item in catalog}
    cited: list[dict[str, Any]] = []
    seen: set[int] = set()
    for match in SOURCE_MARK_RE.finditer(text or ""):
        index = int(match.group(1))
        if index in seen or index not in by_index:
            continue
        seen.add(index)
        cited.append(by_index[index])
    return cited


async def write_retrieval_audit(
    db: AsyncSession,
    *,
    actor_id: UUID,
    patient_id: UUID,
    session_id: UUID,
    query: str,
    intent: Intent,
    chunks: list[RetrievedChunk],
    ip_address: Optional[str] = None,
) -> None:
    await write_audit_log(
        db,
        actor_id=actor_id,
        action="chat.retrieve",
        resource_type="chat_session",
        resource_id=str(session_id),
        ip_address=ip_address,
        metadata={
            "patient_id": str(patient_id),
            "intent": intent.intent,
            "intent_source": intent.source,
            "retrieval_modes": sorted({c.retrieval for c in chunks}),
            "chunk_count": len(chunks),
            "document_ids": [str(c.document_id) for c in chunks],
            "labels": [c.label for c in chunks],
            "query_preview": query[:300],
        },
    )


async def require_patient_session(
    db: AsyncSession, user: User, session_id: UUID
) -> ChatSession:
    if user.role != UserRole.patient:
        raise AppError("Chat is available to patients only", status_code=403, code="patients_only")
    session = await db.get(ChatSession, session_id)
    if not session or session.patient_id != user.id:
        raise AppError("Chat session not found", status_code=404, code="not_found")
    return session


async def create_session(db: AsyncSession, user: User, title: Optional[str] = None) -> ChatSession:
    if user.role != UserRole.patient:
        raise AppError("Chat is available to patients only", status_code=403, code="patients_only")
    session = ChatSession(
        patient_id=user.id,
        title=(title or "New chat").strip()[:255] or "New chat",
        created_at=_utcnow(),
        updated_at=_utcnow(),
    )
    db.add(session)
    await db.flush()
    await write_audit_log(
        db,
        actor_id=user.id,
        action="chat.session_created",
        resource_type="chat_session",
        resource_id=str(session.id),
        metadata={"patient_id": str(user.id)},
    )
    return session


async def list_sessions(
    db: AsyncSession, user: User, *, limit: int = 50
) -> list[ChatSession]:
    if user.role != UserRole.patient:
        return []
    result = await db.execute(
        select(ChatSession)
        .where(ChatSession.patient_id == user.id)
        .order_by(ChatSession.updated_at.desc())
        .limit(max(1, min(limit, 200)))
    )
    return list(result.scalars().all())


async def list_messages(
    db: AsyncSession, user: User, session_id: UUID, *, limit: int = 200
) -> list[ChatMessage]:
    await require_patient_session(db, user, session_id)
    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.desc())
        .limit(max(1, min(limit, 500)))
    )
    return list(reversed(result.scalars().all()))


async def _history_turns(db: AsyncSession, session_id: UUID) -> list[tuple[str, str]]:
    settings = get_settings()
    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.desc())
        .limit(settings.rag_history_turns * 2)
    )
    rows = list(reversed(result.scalars().all()))
    turns: list[tuple[str, str]] = []
    for message in rows:
        role = "user" if message.role == ChatRole.user else "assistant"
        turns.append((role, message.content))
    return turns


def _title_from_query(query: str) -> str:
    compact = " ".join(query.strip().split())
    if len(compact) <= 72:
        return compact
    return compact[:69].rstrip() + "…"


async def persist_user_message(
    db: AsyncSession, session: ChatSession, content: str
) -> ChatMessage:
    message = ChatMessage(
        session_id=session.id,
        role=ChatRole.user,
        content=content.strip(),
        cited_document_ids=[],
        created_at=_utcnow(),
    )
    db.add(message)
    if session.title == "New chat":
        session.title = _title_from_query(content)
    session.updated_at = _utcnow()
    await db.flush()
    return message


async def persist_assistant_message(
    db: AsyncSession,
    *,
    user: User,
    session: ChatSession,
    content: str,
    chunks: list[RetrievedChunk],
    insufficient: bool,
    ip_address: Optional[str] = None,
) -> ChatMessage:
    cited_rows = citations_cited_in_answer(content, chunks) if chunks and not insufficient else []
    cited_ids = list(dict.fromkeys(UUID(str(item["document_id"])) for item in cited_rows))
    message = ChatMessage(
        session_id=session.id,
        role=ChatRole.assistant,
        content=content,
        cited_document_ids=cited_ids,
        citations=cited_rows,
        insufficient_context=insufficient,
        created_at=_utcnow(),
    )
    db.add(message)
    session.updated_at = _utcnow()
    await db.flush()
    await write_audit_log(
        db,
        actor_id=user.id,
        action="chat.qa",
        resource_type="chat_session",
        resource_id=str(session.id),
        ip_address=ip_address,
        metadata={
            "patient_id": str(session.patient_id),
            "message_id": str(message.id),
            "insufficient_context": insufficient,
            "cited_document_ids": [str(i) for i in cited_ids],
        },
    )
    return message


def system_prompt_for(language: str) -> str:
    return GROUNDED_SYSTEM_PROMPT + LANGUAGE_RULES.get(language, "")


def is_insufficient_reply(text: str) -> bool:
    lowered = text.strip().lower()
    return any(lowered.startswith(reply.lower()) for reply in INSUFFICIENT_REPLIES.values())


def sse_pack(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


async def _persist_generation_failure(
    db: AsyncSession,
    *,
    user: User,
    session: ChatSession,
    content: str,
    ip_address: Optional[str] = None,
) -> None:
    try:
        await persist_assistant_message(
            db,
            user=user,
            session=session,
            content=content,
            chunks=[],
            insufficient=False,
            ip_address=ip_address,
        )
        await db.commit()
    except Exception:  # noqa: BLE001
        logger.exception("Could not persist failed chat reply")
        await db.rollback()


async def stream_answer(
    db: AsyncSession,
    *,
    user: User,
    session: ChatSession,
    query: str,
    language: str = "en",
    ip_address: Optional[str] = None,
) -> AsyncIterator[str]:
    insufficient_reply = INSUFFICIENT_REPLIES.get(language, INSUFFICIENT_REPLY)
    intent = await classify_intent(query)
    chunks = await retrieve_for_query(db, session.patient_id, query, intent)
    await write_retrieval_audit(
        db,
        actor_id=user.id,
        patient_id=session.patient_id,
        session_id=session.id,
        query=query,
        intent=intent,
        chunks=chunks,
        ip_address=ip_address,
    )
    await db.commit()

    insufficient = len(chunks) == 0
    citations = citations_from_chunks(chunks)
    yield sse_pack(
        "meta",
        {
            "intent": intent.intent,
            "insufficient_context": insufficient,
            "citations": citations,
        },
    )

    if insufficient:
        assistant = await persist_assistant_message(
            db,
            user=user,
            session=session,
            content=insufficient_reply,
            chunks=[],
            insufficient=True,
            ip_address=ip_address,
        )
        await db.commit()
        yield sse_pack("token", {"text": insufficient_reply})
        yield sse_pack(
            "done",
            {
                "message_id": str(assistant.id),
                "insufficient_context": True,
                "citations": [],
                "cited_document_ids": [],
            },
        )
        return

    history = await _history_turns(db, session.id)
    if history and history[-1][0] == "user":
        history = history[:-1]

    collected: list[str] = []
    try:
        async for token in langchain_llm.stream_grounded_answer(
            system_prompt=system_prompt_for(language),
            context=format_context(chunks),
            query=query,
            history=history,
        ):
            collected.append(token)
            yield sse_pack("token", {"text": token})
    except asyncio.CancelledError:
        await _persist_generation_failure(
            db,
            user=user,
            session=session,
            content="Generation stopped.",
            ip_address=ip_address,
        )
        raise
    except AppError as exc:
        fail_text = exc.message
        await _persist_generation_failure(
            db,
            user=user,
            session=session,
            content=fail_text,
            ip_address=ip_address,
        )
        yield sse_pack("error", {"detail": fail_text, "code": exc.code})
        return
    except Exception as exc:  # noqa: BLE001
        logger.exception("Chat generation failed: %s", exc)
        fail_text = "The assistant could not generate a reply right now."
        await _persist_generation_failure(
            db,
            user=user,
            session=session,
            content=fail_text,
            ip_address=ip_address,
        )
        yield sse_pack("error", {"detail": fail_text})
        return

    text = "".join(collected).strip() or insufficient_reply
    looks_empty = is_insufficient_reply(text)
    assistant = await persist_assistant_message(
        db,
        user=user,
        session=session,
        content=text,
        chunks=[] if looks_empty else chunks,
        insufficient=looks_empty,
        ip_address=ip_address,
    )
    await db.commit()
    used_citations = [] if looks_empty else citations_cited_in_answer(text, chunks)
    yield sse_pack(
        "done",
        {
            "message_id": str(assistant.id),
            "insufficient_context": looks_empty,
            "citations": used_citations,
            "cited_document_ids": [c["document_id"] for c in used_citations],
        },
    )
