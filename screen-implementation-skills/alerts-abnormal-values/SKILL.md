---
name: alerts-abnormal-values
description: Implement the Alerts inbox for the Patient Health Intelligence Platform — surfacing abnormal/critical findings ranked by severity, notification preferences, and the backend alert-dispatch service. Use this whenever the user asks to build the alerts screen, abnormal-value notifications, critical-finding flagging, or notification preference settings for this platform.
---

# Alerts & Abnormal Values Screen

Covers: the alerts inbox UI, notification dispatch (email/push/in-app), and the backend service that turns a severity flag into a delivered alert.

## 1. Purpose
Immediately surface `abnormal`/`critical` findings (flags computed by the Trend/Anomaly service — see `trends-comparison` skill) so nothing important gets buried in a long report list.

## 2. Backend Implementation (FastAPI)

### Endpoints
| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v1/alerts?status=unacknowledged&severity=critical` | List alerts, filterable |
| PATCH | `/api/v1/alerts/{id}/acknowledge` | Mark read/acknowledged |
| GET | `/api/v1/alerts/preferences` | Current notification preferences |
| PATCH | `/api/v1/alerts/preferences` | Update channel (email/push/in-app) per severity level |
| GET | `/api/v1/doctors/me/patient-alerts` | Doctor-side: alerts across their consented patient panel |

### Alert Service
- Subscribes to the event the Trend/Anomaly service emits when a `lab_results`/`imaging_studies` row is flagged `abnormal` or `critical`.
- Creates an `alerts` row: `(patient_id, document_id, severity, message, acknowledged=false, created_at)`. `message` is a short, plain-language one-liner (reuse the patient-explanation LLM output's first sentence rather than generating a separate message).
- Dispatch via Celery beat, respecting `notification_preferences` per severity (e.g., patient wants push for `critical` only, in-app for everything):
  - Email via SES/SMTP provider.
  - Push via FCM/APNs (web push for the browser client).
  - In-app is always created regardless of preference (it's the source of truth; email/push are just delivery channels).
- Doctor-side alerts are derived, not duplicated: query alerts for all patients with an active `consent_grants` row for the requesting doctor.

### Gotchas
- Never dispatch a `critical` alert only through a channel the user might miss — critical severity should always include in-app + at least one out-of-band channel (email/push) regardless of preference, with an explicit UI note explaining why.
- Deduplicate: don't fire a new alert every time a summary regenerates for the same underlying abnormal value — key alert creation off the `lab_results.id`/`flag` transition, not off summary generation events.
- Acknowledging an alert must be logged to `audit_logs` (who acknowledged, when) — this is clinically relevant.

## 3. Frontend Implementation (React)

### Components
- `<AlertsInbox />` — list sorted by severity then recency; unacknowledged items visually distinct (bold/dot indicator).
- `<AlertCard />` — severity badge, one-line message, "View report" and "View trend" deep links, acknowledge button.
- `<NotificationPreferencesForm />` — per-severity channel toggles (email/push/in-app), lives in Profile/Settings but is scoped by this skill.
- `<DoctorAlertsPanel />` — doctor view, grouped by patient, with patient name/DOB header per group.

### State & data flow
- TanStack Query with a short `refetchInterval` (or WebSocket push) so new alerts appear without a manual refresh — this is the one screen where near-real-time matters most.
- Acknowledge is an optimistic mutation (flip the UI immediately, roll back on error).
- Badge count on the main nav (unacknowledged alert count) sourced from the same query, deduped via TanStack Query's cache so it doesn't trigger a second network call.

### UX details
- Keep severity color scale identical to `trends-comparison` and `patient-explanation-view` (green/amber/red).
- Every alert links directly into both the source report (`upload-ingestion`/report detail) and the relevant trend chart (`trends-comparison`) — this screen should never be a dead end.
- Persistent, non-dismissible banner for any `critical` unacknowledged alert until the user opens it (don't let it get lost in a scrollable list).
