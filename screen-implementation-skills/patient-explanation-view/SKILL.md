---
name: patient-explanation-view
description: Implement the patient-facing Plain-Language Explanation screen for the Patient Health Intelligence Platform — translating lab/imaging/prescription findings into empathetic, jargon-free language with severity indicators and "questions to ask your doctor," plus the backend LLM prompt design and reading-level/i18n handling. Use this whenever the user asks to build the patient explanation screen, plain-language summaries, severity color-coding, or reading-level/language controls for this platform.
---

# Patient Explanation View

Covers: LLM-generated plain-language findings, severity visualization, reading-level and language controls.

## 1. Purpose & Output Shape
Empathetic, plain language, structured per finding:
- **What it is** (one sentence, no jargon — define any unavoidable medical term inline)
- **What your result was** (value + severity badge: green/amber/red, tied to reference range)
- **What this means** (context, non-alarming tone, never diagnostic)
- **Questions you might ask your doctor** (2-3 bullets)

## 2. Backend Implementation (FastAPI)

### Endpoints
| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v1/summaries/{document_id}?audience=patient&level=simple|detailed&lang=en` | Retrieve/generate patient explanation |
| POST | `/api/v1/summaries/{document_id}/regenerate?audience=patient` | Force regeneration (e.g., reading-level or language change) |

### LLM prompt design
- Same structured input as the doctor summary (see `doctor-summary-view` skill) — normalized `lab_results`/`prescriptions`/etc, not raw OCR text.
- Two prompt variants selected by `level` param:
  - `simple`: 5th–6th grade reading level, short sentences, everyday analogies.
  - `detailed`: more clinical context but still jargon-explained, for patients who want depth.
- `lang` param drives locale-specific prompt instructions (or a translation pass after generation — pick one strategy and be consistent; translating the *structured data interpretation* per-language, not machine-translating the English output, gives better medical accuracy).
- Hard prompt constraints: no diagnosis, no treatment recommendation, always end high-severity findings with an explicit "please discuss this with your doctor" nudge, cite source `lab_results.id`/`imaging_studies.id` per finding for the frontend to deep-link.
- Severity badge (`normal|borderline|abnormal|critical`) is **not** decided by the LLM — it's computed deterministically by the Trend/Anomaly service (reference-range + statistical logic) and passed into the prompt as a given fact, so the LLM only explains it rather than judging it. This avoids inconsistent LLM-decided severity.
- Store generations in the same `summaries` table as doctor summaries, `audience='patient'`, keyed additionally by `(reading_level, lang)` so each combination is cached rather than regenerated on every view.

### Gotchas
- Cache aggressively per `(document_id, level, lang)` — don't hit the LLM on every screen view.
- Keep the severity-badge color mapping identical to the one used in `alerts-abnormal-values` and `trends-comparison` so patients see one consistent visual language across the whole app.

## 3. Frontend Implementation (React)

### Components
- `<PatientExplanationCard />` — one card per finding, four sub-sections as above, severity-colored left border/badge.
- `<ReadingLevelToggle />` — simple/detailed switch, persists to user profile preference.
- `<LanguageSelector />` — i18n dropdown; re-fetches summary with new `lang`.
- `<AskYourDoctorList />` — the "questions to ask" bullets, with a "Copy to share with doctor" action.

### State & data flow
- TanStack Query keyed by `['summary', documentId, 'patient', level, lang]`; switching the toggle just changes the query key rather than mutating state manually.
- Persist `level`/`lang` preference to `patient_profiles` via a small `PATCH /api/v1/users/me/preferences` call so it's remembered across sessions.

### UX details
- Never show raw medical codes (LOINC/ICD-10) in this view — those belong in the doctor view/export only.
- Pair every severity badge with a plain-language label, not just color (accessibility — don't rely on color alone).
- If a finding is `critical`, this view should visually match the corresponding entry in the Alerts inbox (`alerts-abnormal-values` skill) so the patient recognizes it as the same thing.
