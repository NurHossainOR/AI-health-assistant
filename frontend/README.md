# Frontend (Next.js)

React app using **Next.js 15 App Router**.

## Dev

```bash
npm install
npm run dev
```

Open http://localhost:3000

API requests to `/api/*` are proxied to the FastAPI backend (default `http://127.0.0.1:8000`).

## Structure

```
app/           # Routes (login, signup, dashboard, admin, mfa)
components/    # UI + auth providers + guards
lib/           # API client
types/         # TypeScript types
```

## Docker

Started via root `docker compose up --build` on port **3000**.
