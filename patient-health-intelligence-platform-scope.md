# Patient Health Intelligence Platform — Detailed Technical Scope

**Stack:** React (Frontend) · FastAPI (Backend) · PostgreSQL (Database) · AI/LLM Services (RAG + Document Intelligence)

---

## 1. Executive Summary

A platform where patients upload medical documents (blood tests, prescriptions, MRI/CT scans, discharge summaries), and the system uses OCR/NLP/LLM pipelines to extract structured data, generate dual-audience summaries (doctor-facing and patient-facing), track trends over time, flag abnormalities, and answer natural-language questions via Retrieval-Augmented Generation (RAG) — all behind secure, role-based, encrypted access.

---

## 2. System Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        CLIENT LAYER                              │
│   React SPA (Web) — Patient Portal / Doctor Portal / Admin       │
└───────────────────────────┬───────────────────────────────────────┘
                             │ HTTPS/REST + WebSocket (chat streaming)
┌───────────────────────────▼───────────────────────────────────────┐
│                     API GATEWAY / FASTAPI BACKEND                 │
│  Auth Service │ Document Service │ Report Service │ Chat Service  │
│  Timeline Service │ Notification Service │ Admin/RBAC Service     │
└───────┬───────────────┬───────────────┬───────────────┬───────────┘
        │               │               │               │
┌───────▼──────┐ ┌──────▼───────┐ ┌─────▼──────┐ ┌───────▼────────┐
│ PostgreSQL   │ │ Object Store │ │ Vector DB  │ │ Task Queue      │
│ (structured  │ │ (S3/MinIO -  │ │ (pgvector/ │ │ (Celery+Redis)  │
│ data, users, │ │ raw files:   │ │ Pinecone)  │ │ async pipelines │
│ reports)     │ │ PDFs/DICOM)  │ │ embeddings │ │                 │
└──────────────┘ └──────────────┘ └────────────┘ └────────┬────────┘
                                                            │
                                              ┌─────────────▼─────────────┐
                                              │   AI / ML MICROSERVICES   │
                                              │  OCR │ DICOM Parser       │
                                              │  Medical NER │ Lab Value  │
                                              │  Extractor │ LLM Summarizer│
                                              │  Anomaly Detector │ RAG   │
                                              └───────────────────────────┘
```

**Core design principle:** Uploads trigger an **async ingestion pipeline** (via Celery/Redis) so the UI never blocks on OCR/LLM processing. The frontend polls or subscribes (WebSocket/SSE) for processing status.

---

## 3. Tech Stack Summary

| Layer | Technology |
|---|---|
| Frontend | React 18+, TypeScript, React Router, TanStack Query, Zustand/Redux Toolkit, Tailwind CSS + shadcn/ui, Recharts/Victory for trend charts, react-dropzone for uploads, react-pdf/cornerstone.js for viewing scans |
| Backend API | FastAPI (Python 3.11+), Pydantic v2, SQLAlchemy 2.0 (async) + Alembic migrations |
| Database | PostgreSQL 15+ (with `pgvector` extension for embeddings) |
| Auth | OAuth2 + JWT (access/refresh tokens), FastAPI-Users or custom, optional SSO (Google/Apple) |
| File Storage | AWS S3 / MinIO (self-hosted) with pre-signed URLs |
| Task Queue | Celery + Redis (or RQ) for async document processing |
| OCR | AWS Textract / Google Document AI / Tesseract (self-hosted fallback) |
| DICOM Handling | pydicom, GDCM, Orthanc (DICOM server) for MRI/CT |
| Medical NLP | Med7 / scispaCy / AWS Comprehend Medical for entity extraction (labs, drugs, dosages) |
| LLM | Claude (Anthropic API) for summarization, patient-friendly explanations, and RAG chat |
| Vector Store | pgvector (integrated with Postgres) or Pinecone/Weaviate for embeddings |
| Search/RAG orchestration | LangChain or custom retrieval layer over pgvector |
| Notifications | Celery beat + email (SES) / push (FCM) |
| Infra | Docker, Docker Compose (dev), Kubernetes (prod), Nginx/Traefik, CI/CD via GitHub Actions |
| Monitoring | Prometheus + Grafana, Sentry for error tracking, structured logging (JSON) |
| Security | TLS 1.3, AES-256 at rest, KMS-managed keys, RBAC, audit logging, HIPAA/GDPR-aligned controls |

---

## 4. Frontend Scope (React)

### 4.1 Application Structure

```
src/
├── app/                  # App shell, routing, providers
├── features/
│   ├── auth/             # Login, signup, MFA, password reset
│   ├── upload/            # Document upload & processing status
│   ├── reports/           # Report list, detail, structured data view
│   ├── summaries/          # Doctor summary & patient explanation views
│   ├── trends/             # Trend charts, comparisons
│   ├── timeline/           # Health timeline feature
│   ├── chat/               # RAG-based Q&A chat interface
│   ├── alerts/             # Abnormal value / significant change alerts
│   ├── admin/              # Role/user management (admin only)
│   └── profile/            # Patient profile, linked doctors, consent
├── components/            # Shared UI components (design system)
├── hooks/                 # Shared hooks (useAuth, useUpload, usePolling)
├── lib/                    # API client, query client, utils
├── stores/                 # Zustand/Redux stores (auth, ui state)
└── types/                  # Shared TypeScript types (mirrors backend Pydantic schemas)
```

### 4.2 Roles & Views

| Role | Access |
|---|---|
| **Patient** | Own records only; upload, view summaries, chat, timeline |
| **Doctor** | Records of patients who granted access; doctor-facing summaries, trend views, cannot upload on behalf unless delegated |
| **Caregiver/Family (optional)** | Read-only, granted via patient consent |
| **Admin** | User/role management, audit logs, system health — no clinical data access by default |

### 4.3 Screens & Detailed Behavior

**A. Auth & Onboarding**
- Sign up (email/password + optional SSO), email verification, MFA (TOTP) setup.
- Role selection during onboarding (patient vs. provider), provider identity verification workflow (manual admin approval or NPI lookup integration).
- Consent screen: explicit data-processing consent (required before any upload), granular sharing consent (which doctors can see what).

**B. Upload Center**
- Drag-and-drop / file-picker supporting PDF, JPG/PNG, DICOM (.dcm), common export formats.
- Per-file: document type selector (Blood Test / Prescription / MRI / CT / Discharge Summary / Other) — pre-filled by auto-classification once uploaded, editable by user.
- Multi-file batch upload with individual progress bars.
- Real-time processing status via WebSocket/SSE: `Uploaded → Scanning → Extracting → Validating → Ready` (with failure state + retry).
- Manual correction UI: after OCR/NLP extraction, show extracted fields (test name, value, unit, reference range, date) in an editable table so the patient/doctor can correct misreads before it's saved as "confirmed."

**C. Reports List & Detail**
- Filterable/sortable list (by type, date, doctor, abnormal-flag).
- Detail view: original document viewer (PDF.js for PDFs, cornerstone.js/OHIF viewer for DICOM) side-by-side with structured extracted data.
- Downloadable structured export (CSV/PDF).

**D. Doctor Summary View**
- Clinical, terse, structured: chief findings, abnormal values with deltas from last visit, medication list reconciliation, suggested follow-ups — formatted for quick clinical scanning (bullet-first, no filler).
- Exportable as PDF for clinical handoff.

**E. Patient-Friendly Explanation View**
- Plain-language translation of each finding ("Your LDL cholesterol is a bit higher than the healthy range — this measures the 'bad' cholesterol that can build up in arteries").
- Visual severity indicators (green/amber/red) tied to reference ranges.
- "What this means" / "What you might ask your doctor" sections.
- Reading-level control (simple / detailed) and language selection (i18n).

**F. Trends & Comparisons**
- Multi-select metric comparison (e.g., overlay Hemoglobin A1c across all historical tests) via Recharts line/area charts.
- Auto-detected reference range bands rendered on the chart.
- Date-range filter, export chart as image.
- Side-by-side report comparison table (this test vs. last test vs. reference range, with % change and directional arrows).

**G. Alerts & Abnormal Findings**
- Dedicated "Alerts" inbox: critical/abnormal values surfaced immediately on ingestion, ranked by severity.
- Configurable notification preferences (email/push/in-app) per alert severity.
- Each alert links directly to the source report and the relevant trend chart.

**H. Health Timeline**
- Unified chronological feed across all document types (labs, prescriptions, imaging, discharge events) — vertical timeline UI with type-coded icons.
- Zoomable time axis (week/month/year/all-time).
- Click any timeline node to open the underlying report.
- Filter by condition/tag (e.g., "Diabetes-related events only," auto-tagged via NLP).

**I. AI Chat (RAG)**
- Conversational interface scoped to the patient's own uploaded corpus (with explicit citation of source document/date per answer).
- Suggested starter questions ("What were my last three cholesterol readings?", "Am I due for a follow-up on my MRI finding?").
- Streaming responses (SSE/WebSocket) with inline citations linking to source report.
- Guardrails in UI: disclaimer that chat is informational, not a diagnosis, with a persistent "consult your doctor" note on clinically significant answers.

**J. Profile & Sharing/Consent**
- Manage linked doctors, revoke access, view audit log of who accessed what and when.
- Data export ("download all my data") and account/data deletion (GDPR right-to-erasure flow).

**K. Admin Console**
- User management, role assignment, provider verification queue, system-wide audit log viewer, ingestion pipeline health dashboard (failed jobs, retry queue).

### 4.4 Cross-Cutting Frontend Concerns
- **State management:** TanStack Query for server state/caching; Zustand for local UI/auth state.
- **Accessibility:** WCAG 2.1 AA (important given elderly/patient user base) — large text mode, screen-reader labels on charts (data table fallback).
- **Error handling:** Global error boundary, toast notifications, offline-upload queueing (retry on reconnect).
- **Security in UI:** No PHI in localStorage; tokens in httpOnly cookies or in-memory with refresh rotation; auto-logout on inactivity; screenshot/print watermarking optional.

---

## 5. Backend Scope (FastAPI)

### 5.1 Project Structure

```
backend/
├── app/
│   ├── main.py
│   ├── core/               # config, security, logging, exceptions
│   ├── api/
│   │   └── v1/
│   │       ├── auth.py
│   │       ├── users.py
│   │       ├── documents.py
│   │       ├── reports.py
│   │       ├── summaries.py
│   │       ├── trends.py
│   │       ├── timeline.py
│   │       ├── chat.py
│   │       ├── alerts.py
│   │       ├── consent.py
│   │       └── admin.py
│   ├── models/              # SQLAlchemy ORM models
│   ├── schemas/              # Pydantic request/response schemas
│   ├── services/              # Business logic layer
│   │   ├── auth_service.py
│   │   ├── document_service.py
│   │   ├── ocr_service.py
│   │   ├── nlp_extraction_service.py
│   │   ├── llm_summary_service.py
│   │   ├── trend_service.py
│   │   ├── rag_service.py
│   │   ├── alert_service.py
│   │   └── audit_service.py
│   ├── workers/               # Celery tasks
│   ├── db/                     # session, base, migrations (Alembic)
│   └── tests/
└── requirements.txt
```

### 5.2 Service Responsibilities (Detailed)

**Auth Service**
- Registration, login, JWT issuance (short-lived access token ~15 min, refresh token ~7 days, rotation on use), MFA (TOTP via pyotp), password reset (signed, expiring tokens), session/device management, RBAC middleware (dependency-injected `require_role()` guards on every route).

**Document Service**
- Handles file upload → validates MIME/type/size → generates pre-signed S3 upload URL (or direct multipart upload) → creates `document` DB record with status `pending` → enqueues Celery ingestion task → returns document ID + status-poll endpoint/WebSocket channel.

**OCR Service** (async worker)
- Routes by document type: standard PDFs/images → Textract/Document AI; DICOM → pydicom metadata + pixel extraction (no OCR needed, structured DICOM tags parsed directly).
- Output: raw text + bounding boxes + confidence scores stored for auditability.

**NLP Extraction Service** (async worker)
- Runs medical NER (scispaCy/Comprehend Medical) on OCR text to extract: test names, numeric values, units, reference ranges, dates, prescribing doctor, medication names/dosages/frequency.
- Normalizes test names against a canonical dictionary (e.g., "Hemoglobin A1c" vs "HbA1c" vs "A1C" → single canonical code, ideally mapped to LOINC codes).
- Confidence-scored output routed to "needs review" queue if below threshold — surfaced in frontend's manual-correction UI.

**LLM Summary Service**
- Two distinct prompts/pipelines against the extracted structured data + relevant clinical context:
  1. **Doctor summary**: concise, clinical terminology, structured (findings → deltas → flags → suggested actions).
  2. **Patient explanation**: plain language, empathetic tone, reading-level controlled, includes "questions to ask your doctor."
- Both are regenerated whenever a new document is confirmed, and versioned (summary history retained, not overwritten).
- Explicit prompt-level medical disclaimer injection + no diagnostic claims — outputs framed as informational only.

**Trend/Anomaly Service**
- On each new confirmed lab value, compares against: (a) canonical reference range, (b) patient's own historical values (delta/velocity of change), (c) statistical outlier detection (z-score vs. patient's own baseline).
- Flags: `normal | borderline | abnormal | critical`, triggers Alert Service on `abnormal`/`critical`.

**Alert Service**
- Creates alert records, applies notification preferences, dispatches via Celery beat (email/push), tracks read/acknowledged state, supports doctor-side alert dashboards for their patient panel.

**RAG Service**
- On document confirmation: chunks extracted text + structured summaries → generates embeddings (via Anthropic-compatible embedding model or OpenAI/Voyage embeddings) → stores in pgvector, scoped by `patient_id` (strict tenant isolation — every query is filtered by patient/document ACL before retrieval).
- Chat query flow: embed user question → similarity search (top-k, patient-scoped) → construct context-augmented prompt with citations → stream LLM response → log the Q&A pair (for audit + potential doctor review) → return response with source document references.

**Timeline Service**
- Aggregates all confirmed documents/events into a unified, sortable event stream; auto-tags events by extracted condition/keyword clusters for filtering.

**Consent/Sharing Service**
- Manages patient→doctor grant relationships (scope: all records / specific record types / time-bounded), revocation, and audit trail of every access.

**Audit Service**
- Every read/write of PHI is logged: actor, role, action, resource, timestamp, IP — immutable append-only audit table, exposed via admin/compliance endpoints.

### 5.3 Async Processing Pipeline (Celery Task Chain)

```
upload_document
   └─▶ run_ocr (or dicom_parse)
         └─▶ extract_medical_entities
               └─▶ normalize_and_validate
                     └─▶ [needs_review? → notify_user_for_correction]
                     └─▶ compute_trends_and_flags
                           └─▶ generate_llm_summaries (doctor + patient)
                                 └─▶ generate_embeddings_and_index
                                       └─▶ mark document status = "ready"
                                       └─▶ trigger alerts if abnormal
```
Each step is idempotent and retried with exponential backoff; failures land in a dead-letter queue visible in the admin console.

---

## 6. Database Schema (PostgreSQL) — Core Tables

```sql
-- Users & Roles
users (id, email, password_hash, full_name, role, mfa_enabled, created_at, ...)
roles (id, name)                      -- patient, doctor, caregiver, admin
patient_profiles (user_id FK, dob, sex, height, weight, allergies, ...)
doctor_profiles (user_id FK, npi_number, specialty, verified_at, ...)

-- Consent / Sharing
consent_grants (id, patient_id FK, grantee_id FK, scope, granted_at, revoked_at)

-- Documents & Reports
documents (id, patient_id FK, uploaded_by FK, doc_type, storage_key,
           original_filename, status, uploaded_at, confirmed_at)
document_pages (id, document_id FK, page_number, ocr_text, ocr_confidence)

-- Structured Extracted Data
lab_results (id, document_id FK, patient_id FK, test_code, test_name,
             value, unit, reference_low, reference_high, flag,
             observed_at, source_confidence)
prescriptions (id, document_id FK, patient_id FK, medication_name,
               dosage, frequency, prescribing_doctor, start_date, end_date)
imaging_studies (id, document_id FK, patient_id FK, modality, body_part,
                 findings_text, dicom_metadata JSONB, study_date)
discharge_summaries (id, document_id FK, patient_id FK, diagnosis,
                      procedures, discharge_date, follow_up_instructions)

-- AI Outputs
summaries (id, document_id FK, audience ['doctor'|'patient'], content,
           model_version, generated_at, version_no)
embeddings (id, document_id FK, patient_id FK, chunk_text, embedding VECTOR(1536),
            metadata JSONB)   -- pgvector column

-- Alerts & Timeline
alerts (id, patient_id FK, document_id FK, severity, message,
        acknowledged, created_at)
timeline_events (id, patient_id FK, document_id FK, event_type,
                  event_date, tags TEXT[], summary_snippet)

-- Chat / RAG
chat_sessions (id, patient_id FK, created_at)
chat_messages (id, session_id FK, role ['user'|'assistant'], content,
               cited_document_ids UUID[], created_at)

-- Audit
audit_logs (id, actor_id FK, action, resource_type, resource_id,
            ip_address, metadata JSONB, created_at)
```
Indexing: composite indexes on `(patient_id, observed_at)` for lab_results/trends; IVFFlat/HNSW index on `embeddings.embedding` for pgvector similarity search; row-level security (RLS) policies in Postgres enforcing `patient_id` scoping as a defense-in-depth layer beneath application-level RBAC.

---

## 7. AI Services — Detailed Pipeline

| Stage | Purpose | Candidate Tools |
|---|---|---|
| Document classification | Auto-detect doc type on upload | Lightweight classifier (fine-tuned or LLM zero-shot) |
| OCR | Text/layout extraction from scans/PDFs | AWS Textract, Google Document AI, Tesseract (fallback) |
| DICOM parsing | Extract imaging metadata & render previews | pydicom, GDCM, Orthanc |
| Medical NER | Extract labs, meds, dosages, dates, entities | scispaCy, AWS Comprehend Medical, Med7 |
| Terminology normalization | Map to canonical codes | LOINC (labs), RxNorm (meds), ICD-10 (diagnoses) |
| Summarization (doctor) | Clinical, structured summary | Claude via Anthropic API, deterministic prompt template |
| Summarization (patient) | Plain-language explanation | Claude via Anthropic API, readability-controlled prompt |
| Trend/anomaly detection | Flag abnormal/critical values, deltas | Rule-based (reference ranges) + statistical (z-score on patient baseline) |
| Embeddings/RAG | Semantic search over patient corpus | pgvector + Claude/embedding model, LangChain retrieval chain |
| Chat orchestration | Context-aware Q&A with citations | Claude API (streaming), source-grounded prompting |

**Guardrails across all LLM use:**
- All prompts explicitly instruct: no diagnosis, no treatment prescriptions, cite source data only, flag uncertainty, defer to clinician for decisions.
- Output is always traceable to source document (citation IDs stored alongside generated text).
- Human-in-the-loop: low-confidence extractions and any AI-flagged "critical" value require the flow to prompt human (patient or doctor) review before being marked "confirmed."

---

## 8. API Design (Representative Endpoints)

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/v1/auth/register` | Create account |
| POST | `/api/v1/auth/login` | Login, returns JWT pair |
| POST | `/api/v1/auth/refresh` | Refresh access token |
| POST | `/api/v1/auth/mfa/verify` | MFA challenge verification |
| GET | `/api/v1/users/me` | Current user profile |
| POST | `/api/v1/documents/upload` | Initiate upload, returns pre-signed URL + document ID |
| GET | `/api/v1/documents/{id}/status` | Poll ingestion pipeline status |
| WS | `/ws/documents/{id}/status` | Real-time status stream |
| GET | `/api/v1/documents` | List documents (filterable) |
| GET | `/api/v1/reports/{id}` | Structured extracted data for a report |
| PATCH | `/api/v1/reports/{id}` | Manual correction of extracted fields |
| GET | `/api/v1/summaries/{document_id}?audience=doctor|patient` | Retrieve generated summary |
| GET | `/api/v1/trends?test_code=HbA1c&range=1y` | Time-series values for a metric |
| GET | `/api/v1/timeline` | Unified chronological event feed |
| GET | `/api/v1/alerts` | List alerts, filterable by severity/status |
| PATCH | `/api/v1/alerts/{id}/acknowledge` | Mark alert acknowledged |
| POST | `/api/v1/chat/sessions` | Start chat session |
| POST | `/api/v1/chat/sessions/{id}/messages` | Send message (streams response) |
| POST | `/api/v1/consent/grants` | Grant a doctor access |
| DELETE | `/api/v1/consent/grants/{id}` | Revoke access |
| GET | `/api/v1/admin/audit-logs` | Admin: query audit trail |
| GET | `/api/v1/admin/pipeline-health` | Admin: ingestion job monitoring |

All endpoints: versioned (`/api/v1/`), documented via FastAPI's auto-generated OpenAPI/Swagger, protected by role-based dependency injection, rate-limited per user, and validated with strict Pydantic schemas (reject unknown fields).

---

## 9. Security & Compliance

- **Authentication:** OAuth2 password + refresh flow, JWT (RS256), MFA (TOTP), optional SSO.
- **Authorization:** RBAC enforced at API layer (FastAPI dependencies) + PostgreSQL Row-Level Security as defense-in-depth; every query scoped to `patient_id` unless explicit consent grant exists.
- **Encryption:** TLS 1.3 in transit; AES-256 at rest for DB and object storage; KMS-managed keys with rotation; field-level encryption for highly sensitive columns (e.g., SSN if collected) optional.
- **Audit logging:** Immutable, append-only log of every PHI access/modification (who, what, when, from where).
- **Compliance posture:** Design aligned with HIPAA (US) / GDPR (EU) principles — data minimization, right to access/export/erase, breach notification workflow, Business Associate Agreements (BAAs) with any third-party AI/OCR vendor that touches PHI (critical: verify BAA availability before selecting Textract/Comprehend Medical/Claude API vendor in production).
- **Secrets management:** Vault/AWS Secrets Manager, no secrets in code/env files committed to VCS.
- **Vulnerability management:** Dependency scanning (Dependabot), SAST in CI, periodic penetration testing.
- **Session security:** Short-lived tokens, refresh rotation, device/session revocation, auto-logout on inactivity.

---

## 10. Infrastructure & DevOps

- **Environments:** dev → staging → prod, fully containerized (Docker), orchestrated via Kubernetes in prod.
- **CI/CD:** GitHub Actions — lint/test/build on PR, automated Alembic migration checks, staged deploys with rollback.
- **Observability:** Prometheus + Grafana dashboards (API latency, queue depth, ingestion success rate), Sentry for exceptions, structured JSON logs shipped to a centralized log store (ELK/CloudWatch).
- **Backups:** Automated PostgreSQL point-in-time recovery, S3 versioning + lifecycle policies for uploaded documents.
- **Scaling:** Stateless FastAPI pods behind a load balancer; Celery workers scaled independently by queue depth; read replicas for Postgres as report volume grows.

---

## 11. Feature-to-Component Traceability Matrix

| Requested Feature | Frontend | Backend Service(s) | AI Component |
|---|---|---|---|
| Upload blood tests/prescriptions/MRI/CT/discharge summaries | Upload Center | Document Service, OCR Service | OCR, DICOM parser, NER |
| Doctor summaries | Doctor Summary View | LLM Summary Service | Claude (clinical prompt) |
| Patient plain-language explanations | Patient Explanation View | LLM Summary Service | Claude (patient prompt) |
| Compare results over time / visualize trends | Trends & Comparisons | Trend Service | Statistical delta/z-score |
| Highlight abnormal values/changes | Alerts inbox, inline flags | Trend + Alert Service | Reference-range + anomaly detection |
| Natural-language Q&A (RAG) | Chat interface | RAG Service | Embeddings + Claude streaming |
| Personal health timeline | Timeline view | Timeline Service | Auto-tagging via NLP entities |
| Secure auth, encryption, RBAC | Auth screens, Admin console | Auth, Consent, Audit Services | — |

---

## 12. Suggested Build Phases

1. **Phase 1 — Foundation:** Auth/RBAC, upload pipeline (storage only, no AI), basic report list/detail.
2. **Phase 2 — Extraction:** OCR + NER pipeline, structured lab/prescription data, manual correction UI.
3. **Phase 3 — Intelligence:** LLM summaries (doctor + patient), trend engine, alerts.
4. **Phase 4 — RAG & Timeline:** Embeddings pipeline, chat interface, unified timeline.
5. **Phase 5 — Hardening:** Full audit logging, RLS, compliance review, load testing, admin console.

---

## 13. Open Decisions to Finalize Before Build

- Vector store choice: pgvector (simpler, one DB) vs. dedicated Pinecone/Weaviate (better at scale).
- OCR vendor: cloud (Textract/Document AI, faster to ship, needs BAA) vs. self-hosted Tesseract (more control, more ops burden).
- DICOM viewer: embed OHIF viewer vs. build a lighter custom cornerstone.js viewer.
- Multi-tenancy model: single shared DB with RLS (this doc's default) vs. schema-per-tenant for larger enterprise/hospital deployments.
- Mobile: React web-only initially, or React Native shared-component strategy for a future mobile app.

---

*This document defines the full scope for planning, estimation, and team hand-off. Next step recommendation: convert Section 12 phases into a sprint-level backlog with acceptance criteria per endpoint/screen.*
