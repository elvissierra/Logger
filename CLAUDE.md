# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Full-stack time-tracking application. **Backend**: FastAPI (Python 3.11+) with SQLAlchemy 2.0 + Alembic. **Frontend**: Vue 3 SPA with Vite. **Database**: PostgreSQL (prod) / SQLite (local dev).

## Commands

### Backend (run from `backend/`)
```bash
pip install -r requirements.txt          # Install deps
uvicorn main:app --reload --host localhost --port 8000  # Dev server
alembic upgrade head                     # Run migrations
alembic revision --autogenerate -m "msg" # Generate migration
ruff check .                             # Lint
black .                                  # Format
```

### Frontend (run from `frontend/`)
```bash
npm install        # Install deps
npm run dev        # Dev server (localhost:5173)
npm run build      # Production build
```

### Docker (run from root)
```bash
docker compose up -d --build             # All services
docker compose exec api alembic upgrade head  # Migrations in container
```

## Architecture

### Backend (`backend/`)
Layered architecture: **models → schemas → crud → routes**

- `main.py` — App factory, CORS middleware, router mounting (`/api/auth`, `/api/time-entries`, `/api/projects`)
- `app/core/database.py` — SQLAlchemy engine, `SessionLocal`, `get_db()` dependency
- `app/core/security.py` — JWT creation/verification, password hashing, CSRF validation, cookie management
- `app/core/config.py` — Environment variable loading
- `app/models/` — ORM models: `User`, `TimeEntry`, `Project`
- `app/schemas/` — Pydantic request/response validation
- `app/crud/` — Database operations (separated from route handlers)
- `app/routes/` — API endpoint handlers
- `app/migrations/` — Alembic migration versions

### Frontend (`frontend/src/`)
- `App.vue` — Root component, switches between Login and TimeBoard based on auth state
- `components/Login.vue` — Auth form
- `components/TimeBoard.vue` — Main time logging UI
- `components/TimeCard.vue` — Single time entry; two render modes: full card (focus/today) and compact folder card (weekly grid). Receives `runningId` + `nowTick` from parent (no own timer). Rail button order: edit (SVG pencil) first, start/stop second (■ when running, ⋯ otherwise). Emits `save`, `delete`, `start`, `stop`. Defensive clone of props for editing; datetimes rounded to `incrementMinutes`.
- `components/TodayLog.vue` — "Today Focus" panel; visible only when `layoutMode==='grid'` and the current week is this week. Shows swimlanes with today entries or running timer, sorted running-first. Daily plan textarea persisted to `localStorage` keyed by `userId + dayKey`.
- `components/WeekLog.vue` — 7-day weekly grid (swimlane rows × day columns). Deck hover system: `MAX_DECK_BEHIND=3` stacked entries peek behind the front card; hover expands with `hoverDeltaPx` computed from `scrollHeight` vs `--deck-peek` CSS var; collapse debounced 90 ms.
- `lib/api.js` — HTTP helpers (`apiFetch`, `getJSON`, `postJSON`) with auto-refresh on 401
- `lib/time.js` — Time utility functions

### Authentication
Cookie-based JWT with double-submit CSRF defense:
- Access token (10 min) + refresh token (14 days) in HttpOnly cookies
- `X-CSRF-Token` header required for mutating requests
- Rotating refresh tokens with JTI tracking; `token_version` on User for force-logout
- Frontend dispatches `logger:auth-expired` custom event on unrecoverable 401

### Key DB Details
- Composite index on `TimeEntry(user_id, start_utc)` for weekly queries
- Unique index on `User.email`; index on `User.refresh_jti`
- Running entries have `end_utc = null`
- `User.time_increment_minutes` controls time rounding (1, 5, 10, 15)
