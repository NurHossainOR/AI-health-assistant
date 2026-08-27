---
name: health-timeline
description: Implement the personal Health Timeline screen for the Patient Health Intelligence Platform — a unified, zoomable, chronological feed across all uploaded document types with auto-tagging and condition filtering, plus the backend aggregation service and Postgres model. Use this whenever the user asks to build the health timeline, chronological event feed, condition-based filtering, or cross-document event aggregation for this platform.
---

# Health Timeline Screen

Covers: aggregating every confirmed document into one chronological feed, auto-tagging by condition, and the zoomable timeline UI.

## 1. Purpose
One vertical feed mixing labs, prescriptions, imaging, and discharge events across the patient's entire history, filterable by auto-detected condition tags (e.g., "Diabetes-related events only").

## 2. Backend Implementation (FastAPI)

### Endpoints
| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v1/timeline?from=&to=&tags=diabetes,cardiology` | Paginated, chronological event list |
| GET | `/api/v1/timeline/tags` | Distinct tags available for this patient (populates filter chips) |

### Timeline Service
- On every document confirmation, upsert a `timeline_events` row: `(patient_id, document_id, event_type, event_date, tags, summary_snippet)`.
  - `event_type` maps to the document type (`lab_result`, `prescription`, `imaging`, `discharge`).
  - `event_date` = the clinically relevant date (test collection date, prescription start date, study date, discharge date) — **not** the upload timestamp; these can differ significantly and the timeline must reflect clinical chronology.
  - `tags` derived from the NLP entity extraction step (condition/keyword clusters already produced during ingestion — reuse, don't re-run NLP here) plus a small canonical condition dictionary to consolidate synonyms.
  - `summary_snippet` = a short one-line excerpt from the patient-facing summary (reuse `patient-explanation-view` output's first sentence, don't generate new text).
- This service is purely aggregation/denormalization — it should not call the LLM itself.

### Gotchas
- Backdate correctly: if a patient uploads an old discharge summary today, its `event_date` should be the historical discharge date, so it inserts into the correct place in the timeline, not at the top.
- Paginate by date range (cursor-based on `event_date`), not offset — timelines can span years and offset pagination breaks when new historical documents are uploaded.
- If a document is later corrected (fields changed) or deleted, the corresponding `timeline_events` row must be updated/removed, not left stale.

## 3. Frontend Implementation (React)

### Components
- `<TimelineFeed />` — vertical list, type-coded icons (lab/prescription/imaging/discharge), grouped by month/year headers.
- `<TimelineZoomControl />` — week/month/year/all-time zoom presets; adjusts the date-range query params.
- `<TimelineTagFilter />` — chip-based multi-select sourced from `/timeline/tags`.
- `<TimelineNode />` — individual event card; click opens the underlying report detail (deep link into `upload-ingestion`'s report view).

### State & data flow
- TanStack Query with `useInfiniteQuery` (cursor-based) for smooth infinite-scroll loading as the user scrolls back in time.
- Tag filter and zoom range live in URL query params for shareability/bookmarking, same pattern as `trends-comparison`.

### UX details
- Visual density should scale with zoom level — "all-time" view can collapse consecutive same-type events into a compact cluster ("3 lab tests in March 2025") that expands on click, rather than rendering every node at full size.
- Reuse the same type-coded icon set and severity accent colors used elsewhere (e.g., an abnormal lab event on the timeline should carry the same red accent as in `alerts-abnormal-values`) for visual consistency across the app.
