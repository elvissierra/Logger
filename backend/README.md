uvicorn main:app --reload --host localhost --port 8000
# Logger Backend — FastAPI

This service powers the time tracking app (Auth + Time Entries). It’s a FastAPI API that uses SQLAlchemy, JWT cookies, and CSRF protection designed for a Vue frontend.

---

## Need‑to‑know (architecture in 60 seconds)

- **Auth model**: Cookie‑based JWTs
  - `access_token` (short‑lived) + `refresh_token` (rotated). Cookies are `HttpOnly`, `SameSite=Lax` in dev.
  - A readable `csrf_token` cookie is set for the SPA. For **POST/PATCH/DELETE**, the frontend must send
    `X-CSRF-Token: <csrf_token cookie>` (double‑submit defense).
- **CORS**: Only origins listed in `BACKEND_CORS_ORIGINS` are allowed. You must include your frontend origin
  (e.g. `http://localhost:5173`).
- **Database**: SQLAlchemy engine from `DATABASE_URL`. **Postgres is the required database for production and deployments.**
  - Migrations via Alembic.
  - For experimentation or very quick local dev, you *may* use SQLite (see the example `.env`), but this is not intended for production use.
- **Routers**:
  - `/api/auth/*` — register, login, refresh, revoke_all, logout, me.
  - `/api/time-entries/*` — per‑user CRUD for time entries.

---

## Requirements

- Python **3.11+** (tested with 3.11/3.12/3.13)
- pip / virtualenv (or `uv`/`pipx` if you prefer)
- A database URL (Postgres recommended) or SQLite file path

---

## Quickstart

1) **Clone & enter** the backend folder

```bash
cd backend
```

2) **Create a virtualenv & install**

```bash
python3 -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -U pip
pip install -r requirements.txt
```

3) **Create a `.env`** (in `backend/`) — copy/paste this and adjust as needed

```env
# Core
APP_NAME="Logger API"
DATABASE_URL="postgresql+psycopg://postgres:postgres@localhost:5432/logger"
# For SQLite dev instead, uncomment the following line and comment the Postgres one:
# DATABASE_URL="sqlite:///./logger.db"

# CORS — include your frontend origin(s)
BACKEND_CORS_ORIGINS="http://localhost:5173,http://127.0.0.1:5173"

# Security
SECRET_KEY="dev-change-me"               # set a strong random value in prod
ACCESS_TOKEN_MIN=10                      # short-lived access tokens
REFRESH_TOKEN_DAYS=14                    # refresh rotation window
COOKIE_SECURE=0                          # set to 1 in HTTPS/prod
# COOKIE_DOMAIN=yourdomain.com           # optional, e.g., app.example.com

# Misc
TIMEZONE="America/Chicago"
```

4) **Run DB migrations** (if using Alembic migrations)

```bash
alembic upgrade head
```

If you don’t have migrations yet and you’re using SQLite for dev, tables will be created at startup.

5) **Start the server**

```bash
uvicorn main:app --reload --host localhost --port 8000
```

Open: `http://localhost:8000/docs` (Swagger UI) or `http://localhost:8000/healthz`.

---

## Minimal API tour

### Auth

```bash
# Register
curl -i -X POST http://localhost:8000/api/auth/register \
  -H 'Content-Type: application/json' \
  -d '{"email":"user@example.com","password":"secretpass"}'

# Login
curl -i -X POST http://localhost:8000/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"user@example.com","password":"secretpass"}'

# Check current user (cookies must be sent back by your client)
curl -i http://localhost:8000/api/auth/me

# Refresh (rotates refresh token)
curl -i -X POST http://localhost:8000/api/auth/refresh

# Logout
curl -i -X POST http://localhost:8000/api/auth/logout
```

### Time entries (remember CSRF for write operations)

When logged in via browser, you’ll have a `csrf_token` cookie. For state‑changing requests, include:

```
X-CSRF-Token: <value of csrf_token cookie>
```

Examples:

```bash
# List entries for a week window
curl -i 'http://localhost:8000/api/time-entries/?from=2025-09-15T00:00:00Z&to=2025-09-22T00:00:00Z'

# Create an entry (send CSRF header)
curl -i -X POST http://localhost:8000/api/time-entries/ \
  -H 'Content-Type: application/json' \
  -H 'X-CSRF-Token: <csrf_from_cookie>' \
  -d '{
        "project_code":"BASEBALL",
        "activity":"Design",
        "start_utc":"2025-09-19T14:00:00Z",
        "end_utc":"2025-09-19T16:00:00Z",
        "notes":"[prio:normal] Initial wireframe"
      }'

# Update partial (PATCH)
curl -i -X PATCH http://localhost:8000/api/time-entries/<id> \
  -H 'Content-Type: application/json' \
  -H 'X-CSRF-Token: <csrf_from_cookie>' \
  -d '{"end_utc":"2025-09-19T17:00:00Z"}'

# Delete
curl -i -X DELETE http://localhost:8000/api/time-entries/<id> \
  -H 'X-CSRF-Token: <csrf_from_cookie>'
```

---

## Common pitfalls & fixes

- **401 on `/api/auth/me`**
  - Cookies not set or blocked? Ensure requests use `credentials: "include"` (frontend) and same host/port family
    as your `BACKEND_CORS_ORIGINS` allowlist.
  - Access token expired: frontend should call `/api/auth/refresh` automatically (see `apiFetch` wrapper).
- **CORS error**: Add your frontend origin to `BACKEND_CORS_ORIGINS`. Restart the server after changing.
- **403 CSRF validation failed**: For POST/PATCH/DELETE include `X-CSRF-Token` header equal to the `csrf_token` cookie.
- **bcrypt warning or import errors**: Ensure `bcrypt` is installed (it is via `passlib[bcrypt]`). If you see
  `module 'bcrypt' has no attribute '__about__'`, reinstall `bcrypt`/`passlib` in your venv.
- **email-validator not installed**: Install optional extras used by Pydantic email types
  ```bash
  pip install 'pydantic[email]'
  ```
- **`DATABASE_URL must be set`**: Define it in `.env`. For local dev with SQLite use `sqlite:///./logger.db`.

---

## Environment variables (reference)

| Var | Required | Example | Notes |
| --- | --- | --- | --- |
| `DATABASE_URL` | yes | `postgresql+psycopg://user:pass@localhost:5432/logger` | Or `sqlite:///./logger.db` for dev |
| `BACKEND_CORS_ORIGINS` | yes | `http://localhost:5173` | Comma‑separated list |
| `SECRET_KEY` | yes | `change-me` | Use a strong secret in prod |
| `ACCESS_TOKEN_MIN` | no | `10` | Access token lifetime in minutes |
| `REFRESH_TOKEN_DAYS` | no | `14` | Refresh token rotation window |
| `COOKIE_SECURE` | no | `0` | Set `1` under HTTPS/prod |
| `COOKIE_DOMAIN` | no | `app.example.com` | Needed when serving from a subdomain |
| `TIMEZONE` | no | `America/Chicago` | UI labeling only; data stored in UTC |

---

## Development tips

- Run the frontend on `http://localhost:5173` and keep it in `BACKEND_CORS_ORIGINS`.
- Use your browser DevTools → **Application → Cookies** to inspect `access_token`, `refresh_token`, `csrf_token`.
- Swagger UI at `/docs` lets you poke endpoints quickly; for CSRF, try requests from the app itself.

---

## License

MIT (or your project license)

---

## Deploy with Docker (Compose)

Quick, production-ish setup that builds:
- **db**: Postgres 16
- **api**: FastAPI app (runs Alembic if configured, then starts Uvicorn)
- **frontend**: Built Vue SPA served by nginx on port 8080

**1) Build & run**
```bash
docker compose up -d --build
```
- Frontend: http://localhost:8080
- API: http://localhost:8000 (docs: /docs)

**2) Environment**
Values are defined in `docker-compose.yml`. Update:
- `DATABASE_URL` (uses `postgresql+psycopg` scheme)
- `BACKEND_CORS_ORIGINS` (should include the public URL where the SPA is served)
- `SECRET_KEY`, token lifetimes, and cookie settings for prod (set `COOKIE_SECURE=1` behind HTTPS and consider `COOKIE_DOMAIN`)

**3) Migrations**
On container start, if `alembic.ini` exists, `alembic upgrade head` runs automatically.
If you need to create migrations:
```bash
docker compose exec api alembic revision --autogenerate -m "init"
docker compose exec api alembic upgrade head
```

**4) Health checks**
- DB uses `pg_isready`.
- API exposes `/healthz` and is polled by Compose. Frontend waits for API to be healthy before starting.

**5) Notes**
- For local dev (hot reload), you can switch the `frontend` service to use Vite (`npm run dev` on port 5173) and mount volumes; for production deploys keep the nginx build above.
- To persist database data locally, the `pgdata` volume is used.