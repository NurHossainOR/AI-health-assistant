---
name: upload-ingestion
description: Implement the Document Upload & Ingestion screen for the Patient Health Intelligence Platform — the multi-file uploader, per-file type classification, real-time processing-status pipeline, and manual correction UI, plus the FastAPI endpoints, Celery task chain, and Postgres models behind it. Use this whenever the user asks to build, wire up, or debug the upload flow, the ingestion pipeline, OCR/NLP extraction status, or the "review extracted fields" screen for this platform.
---

# Upload & Ingestion Screen

Covers: drag-and-drop upload, per-file document-type tagging, async OCR/NLP pipeline, real-time status, and human-in-the-loop correction of extracted fields.

## 1. User Flow
1. Patient drags/selects one or more files (PDF, JPG/PNG, DICOM).
2. Frontend requests a pre-signed upload URL per file, uploads directly to object storage.
3. Backend creates a `documents` row (`status=pending`) and enqueues the ingestion chain.
4. Frontend shows a live status chip per file: `Uploaded → Scanning → Extracting → Validating → Ready` (or `Failed`, with retry).
5. If NLP confidence is low on any field, the file lands in `needs_review`; the UI opens an editable table of extracted fields for the user to confirm/correct.
6. On confirm, backend marks the document `confirmed`, which triggers trend computation, summary generation, and embedding indexing (owned by other skills — this skill stops at "confirmed").

## 2. Backend Implementation (FastAPI)

### Endpoints
| Method | Path | Purpose |
|---|---|---|
| POST | `/api/v1/documents/upload-url` | Request a pre-signed S3/MinIO PUT URL; body: `{filename, mime_type, doc_type_hint}` → returns `{document_id, upload_url, storage_key}` |
| POST | `/api/v1/documents/{id}/complete` | Client calls after successful upload to object storage; flips status to `pending` and enqueues the Celery chain |
| GET | `/api/v1/documents/{id}/status` | Poll current pipeline stage |
| WS | `/ws/documents/{id}/status` | Push status changes (preferred over polling) |
| GET | `/api/v1/documents/{id}/extracted-fields` | Return NLP-extracted fields awaiting review |
| PATCH | `/api/v1/documents/{id}/extracted-fields` | Save user corrections; body is the corrected field list |
| POST | `/api/v1/documents/{id}/confirm` | Finalize document after review (or auto-confirm if confidence was high) |
| POST | `/api/v1/documents/{id}/retry` | Re-run a failed pipeline stage |

Validate `mime_type`/extension against an allowlist (`pdf, jpg, jpeg, png, dcm`) and enforce a max size (e.g., 25MB) server-side before issuing the upload URL — never trust the client.

### Celery task chain (idempotent, retried with backoff)
```
run_ocr_or_dicom_parse
  -> extract_medical_entities        # scispaCy / Comprehend Medical / Med7
    -> normalize_terms               # map to LOINC (labs) / RxNorm (meds)
      -> score_confidence            # per-field confidence
        -> [confidence < threshold] -> set status=needs_review, notify_frontend
        -> [confidence >= threshold] -> status=extracted (auto-advance to confirm)
```
Each task writes its output to `document_pages` / `lab_results` / `prescriptions` / `imaging_studies` (draft rows, not yet `confirmed`) so a failure mid-chain doesn't lose prior work. Publish stage transitions to the WebSocket channel keyed by `document_id`.

### Data model touchpoints
- `documents(id, patient_id, uploaded_by, doc_type, storage_key, original_filename, status, uploaded_at, confirmed_at)`
- Draft extraction rows carry `source_confidence` per field; the review UI reads/writes exactly these rows via the `extracted-fields` endpoints.

### Gotchas
- Never process files synchronously in the request/response cycle — always hand off to Celery immediately.
- DICOM files skip OCR entirely; parse tags directly with `pydicom` and store `dicom_metadata` as JSONB.
- Reject/flag duplicate uploads (same patient + same file hash) rather than silently re-ingesting.

## 3. Frontend Implementation (React)

### Components
- `<UploadDropzone />` — wraps `react-dropzone`; accepts multi-file drop; per-file type selector (defaults to "auto-detect", editable).
- `<UploadQueueItem />` — one row per file: filename, doc-type badge, progress bar, status chip, retry button on failure.
- `<ExtractedFieldsReviewTable />` — editable grid (test name, value, unit, reference range, date) shown when a document hits `needs_review`; inline validation (numeric fields, date pickers); "Confirm" button calls `PATCH` then `POST /confirm`.

### State & data flow
- TanStack Query mutation for the upload-URL request + direct `fetch`/`axios` PUT to the pre-signed URL (track progress via `onUploadProgress`).
- Subscribe to `/ws/documents/{id}/status` per in-flight upload; fall back to 3s polling of the status endpoint if WebSocket isn't available.
- Store upload queue in a Zustand slice (`useUploadQueueStore`) keyed by `document_id` so the queue survives navigation away from the upload screen.
- On `needs_review`, route the user to the review table (same screen, expanded panel — don't force a page navigation, it breaks the queue mental model).

### UX details
- Show original doc-type guess but let the user override before or after upload; changing it should not require re-upload, only a `PATCH` to `doc_type`.
- Offline/flaky network: queue uploads locally and retry on reconnect (don't lose a selected file if the PUT fails).
- Never block the "Upload" button on the whole pipeline finishing — patients should be able to queue five files and walk away.
