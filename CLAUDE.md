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
- `app/core/security.py` — JWT creation/verification (HS256, `iss`/`aud` claims bound to `JWT_ISSUER`/`JWT_AUDIENCE` env vars), password hashing, `require_csrf`, cookie management. `SECRET_KEY` validated at startup: ephemeral random key in dev if missing/weak; hard `RuntimeError` in non-dev. Cookie names dynamic: `__Host-` prefix when `COOKIE_SECURE=1` and no `COOKIE_DOMAIN` (`ACCESS_COOKIE`, `REFRESH_COOKIE`, `CSRF_COOKIE` constants).
- `app/core/config.py` — Environment variable loading
- `app/models/` — ORM models: `User`, `TimeEntry`, `Project`
- `app/schemas/` — Pydantic request/response validation
- `app/crud/` — Database operations (separated from route handlers)
- `app/routes/` — API endpoint handlers
- `app/migrations/` — Alembic migration versions

### Frontend (`frontend/src/`)
- `App.vue` — Root component, switches between Login and TimeBoard based on auth state
- `components/Login.vue` — Auth form
- `components/TimeBoard.vue` — Primary authenticated UI. Two layout modes: `grid` (weekly matrix + TodayLog focus area) and `simple` (per-day columns). Owns all state: `runningId` (localStorage `logger.runningEntry:<uid>`), `incrementMinutes` (1–60, default 15, localStorage `logger.incrementMinutes`), `nowTick` (1 s interval, no per-card timers), `swimlanes`, `groupBy`, `currentWeekStart`. Timer logic: `startTimer(seedCard)` starts at exact current time; if a previous stop just occurred the new entry begins at that stop boundary (no gap); `stopRunningIfAny()` calls `snapStopToIncrement(runningCard.start_utc, now)` so stop = start + N×increment (min 1); falls back to `roundDateToIncrement(now, 'ceil')` if running card not found. Stale-pointer detection: 404/already-stopped backend errors clear `runningId` locally and reload. `findRunningCard()` searches swimlanes by id. `assignCardsToGrid()` places entries into lanes and day columns; drag & drop updates times and grouping. `laneVisibleOnDayByProjects(laneKey, dayKey)` hides a lane on days before that project's `created_at`. Priority stored as `[prio:low|normal|high|critical]` prefix in `notes`; `parsePriorityAndCleanNotes()` extracts it. Lane metadata (description + priority) in localStorage via inline editor (`editingLaneKey`, `laneMetaDraft`, `editLaneMeta`/`saveLaneMeta`/`cancelLaneMetaEdit`); no backend schema required. `runningLaneTitle` computed exposes the title of the lane containing the running entry. Passes all actions + state as props to TodayLog and WeekLog. `TARGET_WEEKLY_HOURS = 40`. Theme toggle syncs `<html data-theme>` + `logger.theme`; detects `prefers-color-scheme` as default. All date math in local time for UI; converts to UTC ISO on persist via `composeISOFromLaneAndTime`.
- `components/TimeCard.vue` — Single time entry; two render modes: full card (focus area) and compact folder card (weekly grid). Props: `card`, `openOnMount`, `runningId` (String), `nowTick` (Number), `compact` (Boolean), `tabSide` (`'left'|'right'`), `collapsed` (Boolean), `incrementMinutes` (default 15), `stackIndex` (Number). Emits `save`, `delete`, `start`, `stop`. Defensive clone of props for editing (structuredClone → JSON fallback); never mutates parent. `incMins` computed clamps prop to 1–60. `toLocalInput(iso)` subtracts timezone offset → correct local wall-time datetime-local value; `fromLocalInput(localStr)` → UTC ISO rounded to nearest increment. `durationHours` computed live via `nowTick` when running; `roundedDurationHours` rounds to 0.25 h. `onSave` clamps end < start to start + 1 increment; maps `jobTitle`→`job_title`, `projectCode`→`project_code`. Rail button order: edit (SVG pencil) first, start/stop second (■ when running, ⋯ otherwise). Advanced editor fields hidden by default (`showAdvanced` ref); auto-focuses first advanced field on expand. Auto-opens editor for `tmp_` ids or `openOnMount=true`. Keyboard: Cmd/Ctrl+S saves, Escape cancels. Priority shown as `prio-dot` in full card header.
- `components/TodayLog.vue` — "Today Focus" inboard panel; visible only when `layoutMode==='grid'` and the current week is this week (`isSameDay(currentWeekStart, startOfWeek(new Date()))`). `todayLanes` computed: swimlanes filtered to lanes that pass `laneVisibleOnDayByProjects` AND have entries today or a running timer; sorted running-first. Each lane entry: `{ lane, col, sorted (most-recent-first), primary, older, running, meta, todayHours }`. Layout: aside (daily plan textarea) + focus column (swimlane cards with start/stop ▶︎/■, edit meta ⋯, add ＋ actions). Daily plan textarea persisted to `localStorage` key `logger.dailyPlan:<uid>:<dayKey>`; reloads on `todayKey` change. Receives all actions/state from TimeBoard as props; `onCellChange` and `onReorderCell` are optional (backward-compat).
- `components/WeekLog.vue` — 7-day weekly grid (swimlane rows × day columns). Deck hover system: `MAX_DECK_BEHIND=3` stacked entries peek behind the front card; `onDeckEnter` measures `scrollHeight` vs CSS `--deck-peek` var on `.deck` element to compute `hoverDeltaPx`; collapse debounced 90 ms via `_leaveTimer` + `_hoverToken` guard; `onFrontEnter(deckId)` clears hover state only when the same deck is active. Lane row header shows `laneHours`, `laneEntryCount`, running indicator, start/stop + meta edit (⋯) buttons. Props include `laneHours`, `laneEntryCount`, `cellHours`, `laneDesc` aggregation helpers (computed/passed from TimeBoard).
- `lib/api.js` — HTTP helpers (`apiFetch`, `getJSON`, `postJSON`, `patchJSON`, `del`, `onAuthExpired`). `getCsrf()` tries `__Host-csrf_token` cookie first, then falls back to plain `csrf_token`. `apiFetch` skips refresh for auth endpoints; concurrent 401s share one `refreshOnce()` single-flight promise (prevents JTI reuse detection from killing a valid session); dispatches `logger:auth-expired` event on unrecoverable 401.
- `lib/time.js` — Time utility functions

### Authentication
Cookie-based JWT with double-submit CSRF defense:
- Access token (10 min) + refresh token (14 days) in HttpOnly cookies; cookie names use `__Host-` prefix in prod (`COOKIE_SECURE=1`, no `COOKIE_DOMAIN`) for browser-enforced host binding
- All JWTs carry `iss` (`JWT_ISSUER`) and `aud` (`JWT_AUDIENCE`) claims; `decode_token()` validates both
- `X-CSRF-Token` header required for mutating requests; `/refresh` and `/logout` also enforce CSRF via `require_csrf()`
- Rotating refresh tokens with JTI tracking; reuse detection (RFC 6819 §5.2.2.3): JTI mismatch or hash mismatch bumps `token_version`, clears stored refresh state, and forces re-login
- `token_version` on User enables force-logout of all sessions via `/revoke_all`
- Frontend single-flights refresh calls (`refreshOnce()`) to prevent concurrent 401s from triggering reuse detection
- Frontend dispatches `logger:auth-expired` custom event on unrecoverable 401

### Key DB Details
- Composite index on `TimeEntry(user_id, start_utc)` for weekly queries
- Unique index on `User.email`; index on `User.refresh_jti`
- Running entries have `end_utc = null`
- `User.time_increment_minutes` controls time rounding (1, 5, 10, 15)
