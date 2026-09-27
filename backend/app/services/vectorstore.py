from __future__ import annotations

import asyncio
import logging
import os
from functools import lru_cache
from typing import Any
from uuid import UUID

os.environ.setdefault("ANONYMIZED_TELEMETRY", "FALSE")

import chromadb
from chromadb.config import Settings as ChromaSettings
from langchain_chroma import Chroma
from langchain_core.documents import Document as LCDocument
from langchain_google_genai import GoogleGenerativeAIEmbeddings

from app.core.config import get_settings
from app.core.exceptions import AppError
from app.services.vector_filters import patient_metadata_filter

logger = logging.getLogger(__name__)


def _embedding_model_name() -> str:
    name = get_settings().gemini_embedding_model
    if not name.startswith("models/"):
        return f"models/{name}"
    return name


@lru_cache
def get_embeddings() -> GoogleGenerativeAIEmbeddings:
    settings = get_settings()
    if not settings.gemini_api_key:
        raise AppError(
            "Chat is not configured. Set GEMINI_API_KEY on the server.",
            status_code=503,
            code="gemini_unconfigured",
        )
    return GoogleGenerativeAIEmbeddings(
        model=_embedding_model_name(),
        google_api_key=settings.gemini_api_key,
    )


def get_chroma_client() -> chromadb.HttpClient:
    settings = get_settings()
    try:
        return chromadb.HttpClient(
            host=settings.chroma_host,
            port=settings.chroma_port,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
    except Exception:
        return chromadb.HttpClient(host=settings.chroma_host, port=settings.chroma_port)


def get_vectorstore() -> Chroma:
    settings = get_settings()
    return Chroma(
        client=get_chroma_client(),
        collection_name=settings.chroma_collection,
        embedding_function=get_embeddings(),
    )


def delete_document_chunks(document_id: UUID | str) -> None:
    settings = get_settings()
    collection = get_chroma_client().get_or_create_collection(settings.chroma_collection)
    collection.delete(where={"document_id": str(document_id)})


def add_chunks(passages: list[dict[str, Any]]) -> int:
    if not passages:
        return 0
    documents = [
        LCDocument(page_content=item["chunk_text"], metadata=item["metadata"])
        for item in passages
    ]
    ids = [
        f"{item['metadata']['document_id']}:{item['metadata'].get('chunk_kind', i)}"
        for i, item in enumerate(passages)
    ]
    get_vectorstore().add_documents(documents, ids=ids)
    return len(documents)


def has_document_chunks(document_id: UUID | str) -> bool:
    client = get_chroma_client()
    settings = get_settings()
    collection = client.get_or_create_collection(settings.chroma_collection)
    result = collection.get(where={"document_id": str(document_id)}, limit=1)
    return bool(result and result.get("ids"))


def similarity_search(query: str, patient_id: UUID, *, k: int) -> list[LCDocument]:
    """LangChain similarity search, always scoped to one patient_id."""
    filt = patient_metadata_filter(patient_id)
    docs = get_vectorstore().similarity_search(query, k=k, filter=filt)
    scoped: list[LCDocument] = []
    for doc in docs:
        meta_pid = str((doc.metadata or {}).get("patient_id") or "")
        if meta_pid != str(patient_id):
            logger.error("Dropped cross-patient Chroma hit for patient %s", patient_id)
            continue
        scoped.append(doc)
    return scoped


async def adelete_document_chunks(document_id: UUID | str) -> None:
    await asyncio.to_thread(delete_document_chunks, document_id)


async def aadd_chunks(passages: list[dict[str, Any]]) -> int:
    return await asyncio.to_thread(add_chunks, passages)


async def asimilarity_search(query: str, patient_id: UUID, *, k: int) -> list[LCDocument]:
    return await asyncio.to_thread(similarity_search, query, patient_id, k=k)
