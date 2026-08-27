---
name: rag-chat
description: Implement the natural-language Q&A chat screen for the Patient Health Intelligence Platform — a RAG (Retrieval-Augmented Generation) interface scoped strictly to one patient's own uploaded records, with streaming responses and inline source citations, plus the embeddings pipeline, pgvector retrieval, and FastAPI streaming endpoint behind it. Use this whenever the user asks to build the chat/ask-a-question feature, RAG pipeline, embeddings indexing, or streaming chat responses for this platform.
---

# RAG Chat Screen

Covers: the embeddings/indexing pipeline, patient-scoped retrieval, streaming LLM chat with citations, and the chat UI.

## 1. Purpose & Guardrails
Let a patient ask natural-language questions about their own records ("What were my last three cholesterol readings?"). This is the highest-risk feature for scope leakage (must never answer using another patient's data) and for overreach (must never diagnose) — treat both as hard requirements, not nice-to-haves.

## 2. Backend Implementation (FastAPI)

### Indexing pipeline (runs after a document is confirmed — chains off `upload-ingestion`)
1. Chunk the document's structured summary + key extracted fields into short passages (not raw OCR dump — chunk the *normalized* data so retrieval quality doesn't depend on OCR noise).
2. Generate embeddings (Anthropic-compatible embedding model, or Voyage/OpenAI embeddings) for each chunk.
3. Insert into `embeddings(document_id, patient_id, chunk_text, embedding VECTOR(1536), metadata JSONB)` — `patient_id` is stored redundantly on every row specifically so retrieval can filter on it directly without a join, and so a bug in a join can't accidentally leak cross-patient data.

### Endpoints
| Method | Path | Purpose |
|---|---|---|
| POST | `/api/v1/chat/sessions` | Start a session, returns `session_id` |
| POST | `/api/v1/chat/sessions/{id}/messages` | Send a message; **streams** the response (SSE or WebSocket) |
| GET | `/api/v1/chat/sessions/{id}/messages` | Full history for a session |
| GET | `/api/v1/chat/sessions` | List a patient's past sessions |

### RAG Service — retrieval + generation flow
1. Embed the incoming user question.
2. `pgvector` similarity search (`embedding <-> query_embedding`, top-k ~6) with a **mandatory** `WHERE patient_id = :current_patient_id` filter applied at the query-builder level, not left to the LLM or to RLS alone — defense in depth, but the explicit filter is non-negotiable and should be unit-tested.
3. Build a context-augmented prompt: system instructions (no diagnosis, no treatment advice, answer only from provided context, say "I don't have that information in your records" if the context doesn't cover it) + retrieved chunks (each tagged with its source `document_id`/date) + conversation history + the question.
4. Stream the LLM response token-by-token to the client (SSE recommended over WebSocket here for simplicity with standard HTTP infra).
5. Persist the exchange to `chat_messages(session_id, role, content, cited_document_ids, created_at)` — `cited_document_ids` extracted from which chunks were actually used, enabling the frontend to render citation links.
6. Log every Q&A pair to `audit_logs` (chat content involving PHI is itself PHI).

### Gotchas
- Row-Level Security in Postgres should also enforce `patient_id` scoping on the `embeddings` table as a second layer beneath the application filter.
- If retrieval returns zero relevant chunks above a similarity threshold, don't force the LLM to answer — explicitly instruct it to say it doesn't have enough information, rather than let it fall back to general medical knowledge (which would be indistinguishable from a diagnosis to the patient).
- Cap conversation history sent to the LLM (e.g., last 10 turns) to control token cost; older turns are still stored and viewable in history.

## 3. Frontend Implementation (React)

### Components
- `<ChatWindow />` — message list + input box, standard chat UI pattern.
- `<ChatMessage />` — renders assistant messages with inline citation chips (e.g., "[Blood Test, Jan 12]") that link to the source report.
- `<SuggestedQuestions />` — starter prompt chips shown on an empty session ("What were my last three cholesterol readings?", "Am I due for a follow-up on my MRI finding?").
- `<ChatDisclaimerBanner />` — persistent, non-dismissible note: informational only, not a diagnosis, consult your doctor for medical decisions.

### State & data flow
- Use `EventSource` (SSE) or a WebSocket hook to consume the streamed response token-by-token, appending to the last assistant message in local state as chunks arrive.
- TanStack Query for session list/history; the active session's live stream is handled outside the query cache (append-only local state), then reconciled into the cache once the stream completes.
- Session list in a sidebar/drawer, similar to a typical chat product pattern.

### UX details
- Every assistant answer that cites data must show visible citation chips — never render an unsourced clinical claim.
- If the backend returns the "not enough information" fallback, render it distinctly (muted styling) rather than as a normal answer, so the patient doesn't mistake "I don't know" for a reassuring "normal" result.
- Keep the disclaimer banner visible at all times in this screen specifically — this is the feature most likely to be mistaken for medical advice.
