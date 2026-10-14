# Patient Health Intelligence Platform

Phase 1 foundation: authentication, RBAC, consent, audit logging, and admin console.

## Stack

- **Frontend:** Next.js 15 (React) + TypeScript + TanStack Query
- **Backend:** FastAPI + SQLAlchemy (async) + PostgreSQL
- **Auth:** RS256 JWT (30 min access / 7 day refresh with rotation), httpOnly refresh cookie, MFA (TOTP)

## Quick start

### Option A — full stack with Docker (recommended)

**Prerequisites:** Docker + Docker Compose, JWT keys in `keys/` (see Notes below).

```bash
# From repo root
docker compose up --build
```

| Service | URL |
|---|---|
| Frontend | http://localhost:3000 |
| Backend API / docs | http://localhost:8000 / http://localhost:8000/docs |
| Postgres (host access) | `localhost:5433` |

Run in background:

```bash
docker compose up --build -d
docker compose logs -f api web   # follow app logs
docker compose down              # stop everything
```

Default admin is created automatically on first API start: `admin@example.com` / `AdminPass123!`

**Infra only** (run backend/frontend locally against Docker Postgres):

```bash
docker compose up -d db redis
```

Postgres listens on **localhost:5433** (avoids conflict with a local Postgres on 5432).

### Option B — local dev (no Docker for app code)

#### 1. Database

```bash
docker compose up -d db
```

#### 2. Backend

```bash
cd backend
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # if needed
python scripts/create_admin.py   # admin@example.com / AdminPass123!
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

API docs: http://127.0.0.1:8000/docs

#### 3. Frontend

```bash
cd frontend
npm install
npm run dev
```

App: http://localhost:3000

API calls are proxied through Next.js (`/api/*` → backend). Optional override: set `NEXT_PUBLIC_API_URL=http://localhost:8000` in `frontend/.env.local`.

## Implemented (auth-security-rbac skill)

| Area | Details |
|---|---|
| **Auth API** | `POST /api/v1/auth/register`, `login`, `refresh`, `logout`, `mfa/setup`, `mfa/verify`, `password-reset`, `verify-email`, `GET /me` |
| **Consent** | Grant / revoke / list with scope preview for patients |
| **Admin** | User list, doctor approval queue, audit log viewer (metadata only), pipeline health stub |
| **Security** | RS256 JWT, refresh rotation + reuse detection, RBAC dependencies, audit logging, PostgreSQL RLS policies |
| **Frontend** | Login/signup, AuthProvider (in-memory access token + cookie refresh), 15 min inactivity logout, route guards, consent & admin screens |
