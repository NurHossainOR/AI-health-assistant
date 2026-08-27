---
name: trends-comparison
description: Implement the Trends & Comparisons screen for the Patient Health Intelligence Platform — multi-metric time-series charts, reference-range bands, report-to-report comparison tables, and the backend trend/anomaly computation service. Use this whenever the user asks to build trend charts, historical comparisons, delta calculations, reference-range visualization, or the statistical anomaly-detection logic for this platform.
---

# Trends & Comparisons Screen

Covers: time-series visualization of lab values across all historical documents, and the deterministic backend logic that computes deltas/flags (consumed by summaries and alerts too).

## 1. Purpose
Let patients/doctors see how a metric (e.g., HbA1c, LDL) has moved over time against its reference range, and compare any two reports side by side.

## 2. Backend Implementation (FastAPI)

### Endpoints
| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v1/trends?test_code=HbA1c&range=1y` | Time-series points for one canonical test code: `[{value, unit, observed_at, reference_low, reference_high, flag}]` |
| GET | `/api/v1/trends/metrics` | List of test codes this patient has history for (populates the metric picker) |
| GET | `/api/v1/reports/compare?a={document_id}&b={document_id}` | Side-by-side structured comparison of two reports, with per-field % change and directional arrow |

### Trend/Anomaly Service (the deterministic core other screens depend on)
This is the **single source of truth** for severity flags — `patient-explanation-view`, `doctor-summary-view`, and `alerts-abnormal-values` all consume its output rather than recomputing it.

Logic, run whenever a `lab_results` row is confirmed:
1. **Reference-range check**: flag `abnormal` if outside `[reference_low, reference_high]`, `critical` if outside a wider critical-range table (maintain a `critical_ranges` lookup separate from lab-report-printed ranges, since printed ranges vary by lab).
2. **Patient-baseline delta**: compute % change vs. the patient's own immediately-prior confirmed value for the same `test_code`.
3. **Statistical outlier**: z-score of the new value against the patient's own historical mean/stddev for that test_code (needs ≥3 prior points; skip this check otherwise) — flags `borderline` even inside the printed reference range if it's a sharp deviation from the patient's personal baseline.
4. Final flag = the most severe of (1) and (3): `normal < borderline < abnormal < critical`.
5. Write the flag onto the `lab_results` row itself (don't recompute on every read) and emit an event for the Alert Service to consume if `abnormal`/`critical`.

### Gotchas
- Always query by canonical `test_code` (LOINC-normalized), never by the raw extracted test name string — otherwise "HbA1c" vs "Hemoglobin A1c" fragment the trend line.
- Reference ranges can differ by lab/units — normalize units server-side before comparison (e.g., mg/dL vs mmol/L for glucose) and store the normalized unit alongside the original.
- Comparison endpoint should diff on `test_code`, not on array position — reports don't always contain the same set of tests.

## 3. Frontend Implementation (React)

### Components
- `<MetricPicker />` — multi-select of available test codes (from `/trends/metrics`), drives which lines render.
- `<TrendChart />` — Recharts `LineChart`/`AreaChart`; reference-range rendered as a shaded `ReferenceArea`; points colored by `flag` severity; date-range brush/zoom control.
- `<ReportComparisonTable />` — rows = test_code, columns = Report A / Report B / Reference Range / % Change (with ↑/↓ arrow, colored by direction+severity).
- `<ExportChartButton />` — export current chart view as PNG.

### State & data flow
- TanStack Query per selected metric (`['trend', testCode, range]`), fetched in parallel when multiple metrics are selected; combine into one chart dataset client-side (align by date, forward-fill gaps only visually, never in the underlying data).
- Date-range filter persisted in the URL query string so a specific trend view is shareable/bookmarkable.

### UX details
- Always render the reference-range band so a "normal" value's proximity to the edge is visible at a glance.
- Provide a screen-reader-accessible data table fallback for every chart (accessibility requirement carried over from the platform-wide a11y standard).
- Keep the severity color scale (green/amber/red for normal/borderline/abnormal-critical) identical to `patient-explanation-view` and `alerts-abnormal-values`.
