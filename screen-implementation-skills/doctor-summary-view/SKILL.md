---
name: doctor-summary-view
description: Implement the clinician-facing Doctor Summary screen for the Patient Health Intelligence Platform — concise, structured clinical summaries (findings, deltas, flags, suggested follow-ups) generated from a patient's uploaded records, plus the FastAPI/LLM service and Postgres versioning behind it. Use this whenever the user asks to build the doctor summary, clinical summary generation, PDF export for clinicians, or summary versioning/history for this platform.
---

# Doctor Summary View

Covers: LLM-generated clinical summaries, versioning, PDF export, and the screen doctors use to scan a patient's record quickly.

## 1. Purpose & Output Shape
Terse, clinical, structured — not conversational. Standard sections, in this order:
1. **Chief findings** (bulleted, most recent document first)
2. **Abnormal values with deltas** ("LDL 165 mg/dL, ↑12% from 3mo prior; above reference range 100 mg/dL")
3. **Medication reconciliation** (active meds, recent changes, potential interactions flagged, not diagnosed)
4. **Suggested follow-ups** (framed as prompts, e.g., "Consider re-checking A1c in 3 months" — never a directive/diagnosis)

## 2. Backend Implementation (FastAPI)

### Endpoints
| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v1/summaries/{document_id}?audience=doctor` | Latest doctor summary for a document |
| GET | `/api/v1/summaries/{document_id}/history` | All prior versions (never overwritten) |
| POST | `/api/v1/summaries/{document_id}/regenerate` | Force regeneration (e.g., after a correction to extracted fields) |
| GET | `/api/v1/summaries/{document_id}/export.pdf` | Render current summary as a downloadable PDF |

### LLM Summary Service
- Triggered automatically at the end of the ingestion chain once a document is `confirmed` (see `upload-ingestion` skill), and on-demand via `/regenerate`.
- Input to the prompt: structured `lab_results` / `prescriptions` / `imaging_studies` / `discharge_summaries` rows for this document **plus** the patient's prior confirmed values for the same test codes (for delta computation) — do not pass raw OCR text, pass normalized structured data so the LLM isn't guessing at units/ranges.
- Prompt contract (enforce via system prompt + Pydantic-validated structured output):
  - Clinical terminology, no plain-language rephrasing.
  - Every abnormal value must cite the source `lab_results.id` so the frontend can deep-link.
  - No diagnostic claims, no treatment directives — output is informational/decision-support only.
  - Reject/flag if required structured fields are missing rather than hallucinating values.
- Store each generation as a new row in `summaries(document_id, audience='doctor', content, model_version, generated_at, version_no)` — append-only, so doctors can see how a summary changed after a patient corrected a field.

### Gotchas
- Regenerate the summary whenever the underlying extracted fields change (correction flow from `upload-ingestion` should call this).
- Rate-limit `/regenerate` per document to avoid runaway LLM cost from repeated manual triggers.
- PDF export should render from the stored `content` (already-generated text), not re-call the LLM at export time.

## 3. Frontend Implementation (React)

### Components
- `<DoctorSummaryPanel />` — section-based layout matching the four output sections above; each abnormal-value line links to `<ReportDetail />` for that source document.
- `<SummaryVersionHistory />` — collapsible list of prior versions with timestamps, diff-highlighted against the current version.
- `<ExportSummaryButton />` — triggers the PDF export endpoint, opens in new tab / triggers download.

### State & data flow
- TanStack Query `useQuery(['summary', documentId, 'doctor'])`; invalidate on any correction to the document's extracted fields (cross-invalidate from the `upload-ingestion` mutation).
- Role-gate this view: only render for users with `role=doctor` (with valid consent grant for this patient) or `role=patient` viewing their own "what my doctor sees" preview — enforce the actual data access at the API layer via RBAC + consent checks, the frontend gate is UX only.

### UX details
- Bullet-first, dense layout — doctors are scanning, not reading prose. Avoid large blocks of text.
- Surface the model version / generation timestamp unobtrusively (small caption) for clinical traceability.
- If a summary is stale (source document has uncommitted corrections pending review), show a "pending update" badge rather than a silently outdated summary.
