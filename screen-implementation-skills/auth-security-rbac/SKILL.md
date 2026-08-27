---
name: auth-security-rbac
description: Implement authentication, role-based access, consent/sharing, and the admin console for the Patient Health Intelligence Platform — signup/login/MFA, doctor-patient consent grants, audit logging, and encryption, spanning the FastAPI auth service and every React screen that gates access (login, consent management, admin console). Use this whenever the user asks to build login/signup, MFA, role-based access control, patient-doctor consent/sharing, audit logs, or the admin console for this platform.
---

# Auth, Security, Consent & Admin Screens

Covers: registration/login/MFA, RBAC enforcement, patient→doctor consent grants, audit logging, and the admin console. This skill underpins every other screen — read it alongside whichever feature skill you're implementing if that feature touches PHI (all of them do).

## 1. Roles & Access Model
| Role | Access |
|---|---|
| `patient` | Own records only |
| `doctor` | Records of patients with an active `consent_grants` row naming them, scoped to whatever the grant permits |
| `caregiver` | Read-only, granted via patient consent (optional) |
| `admin` | User/role management, audit logs, pipeline health — **no** clinical data access by default |

## 2. Backend Implementation (FastAPI)

### Endpoints
| Method | Path | Purpose |
|---|---|---|
| POST | `/api/v1/auth/register` | Create account; role selection; triggers email verification |
| POST | `/api/v1/auth/login` | Returns JWT access + refresh token pair |
| POST | `/api/v1/auth/refresh` | Rotates refresh token, issues new access token |
| POST | `/api/v1/auth/mfa/setup` | Returns TOTP secret/QR |
| POST | `/api/v1/auth/mfa/verify` | Verifies TOTP code during login |
| POST | `/api/v1/auth/password-reset` | Signed, expiring reset token flow |
| POST | `/api/v1/consent/grants` | Patient grants a doctor access (scope: all / specific doc types / time-bounded) |
| DELETE | `/api/v1/consent/grants/{id}` | Revoke |
| GET | `/api/v1/consent/grants` | List active/past grants (patient view) or grants-to-me (doctor view) |
| GET | `/api/v1/admin/users` | Admin: list/manage users, approve doctor verification |
| GET | `/api/v1/admin/audit-logs?actor=&resource=&from=&to=` | Admin: query the audit trail |
| GET | `/api/v1/admin/pipeline-health` | Admin: ingestion job success/failure dashboard |

### Core mechanics
- **JWT**: RS256, short-lived access token (~30 min), refresh token (~7 days) with rotation-on-use (reject reused refresh tokens — signals token theft).
- **RBAC**: implement as a FastAPI dependency, e.g. `require_role(["doctor", "admin"])`, applied per-route; every clinical-data route additionally checks a resource-level consent function (`patient_id == current_user.id OR active_grant_exists(current_user.id, patient_id)`), not just the role.
- **Row-Level Security**: mirror the same `patient_id` scoping as a Postgres RLS policy on every PHI table, as defense-in-depth beneath the application-layer check — a bug in one layer shouldn't be a full breach.
- **Audit Service**: every read or write of a PHI-bearing table logs `(actor_id, action, resource_type, resource_id, ip_address, metadata, created_at)` to an append-only `audit_logs` table. Implement as a shared FastAPI dependency/middleware wrapping the relevant routes rather than scattering log calls through business logic, so nothing is missed.
- **Encryption**: TLS in transit; AES-256 at rest for DB/object storage; secrets via a vault/secrets manager, never in env files committed to source control.
- **Doctor verification**: registration as `doctor` role lands the account in `status=pending_verification`; admin console approves after NPI lookup / manual check before any consent grant can target that account.

### Gotchas
- Never let a `doctor`-role query bypass the consent check just because the role matches — role is necessary but not sufficient.
- Revoking a consent grant should immediately invalidate any cached/derived data (e.g., a doctor's dashboard) — don't rely solely on TTL cache expiry for something this sensitive.
- Verify BAA (Business Associate Agreement) coverage for any third-party vendor (OCR, LLM, email) that touches PHI before wiring it into production — this is a compliance blocker, not an implementation detail, but it belongs on this skill's checklist since auth/consent is where compliance responsibility concentrates.

## 3. Frontend Implementation (React)

### Components
- `<LoginForm />` / `<SignupForm />` — role selection during signup, email verification prompt.
- `<MfaSetup />` / `<MfaChallenge />` — QR display + code entry.
- `<ConsentManager />` (patient view) — list of doctors with access, grant scope editor, revoke button, "who accessed my data" audit excerpt.
- `<ConsentRequestReview />` (doctor view) — pending/active grants to this doctor.
- `<AdminConsole />` — user table with role/status filters, doctor-verification approval queue, `<AuditLogViewer />` (filterable table), `<PipelineHealthDashboard />` (failed/retrying ingestion jobs from the `upload-ingestion` pipeline).

### State & data flow
- Auth tokens: access token in memory (not localStorage — XSS risk with PHI at stake), refresh token in an httpOnly cookie; a top-level `AuthProvider` handles silent refresh and 401-triggered logout.
- Route guards (`<RequireRole roles={[...]}>`) wrap every screen from every other skill in this set — this is the enforcement point on the frontend, mirrored (and actually enforced) server-side.
- Inactivity auto-logout timer reset on user interaction, configurable but default conservative (e.g., 15 min) given PHI sensitivity.

### UX details
- Consent grant creation should show the patient exactly what the doctor will see (a preview), not just an abstract scope name — reduces accidental over-sharing.
- Admin console must never render clinical field values, only metadata (user, action, resource type/id, timestamp) — keep this boundary strict even for debugging convenience.
