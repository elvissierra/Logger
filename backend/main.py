"""
Knowledge Drop — backend/main.py (FastAPI app factory and wiring)

What this file does
- Builds the FastAPI app, installs security/CORS middlewares, mounts routers, and exposes health endpoints.

How it works with other resources
- CORS allowlist is parsed from env; CORSMiddleware is installed before routers so all responses include headers.

Why it’s necessary
- Single composition point for the API; keeps route modules small and focused.

Notes
- In production, set TRUSTED_HOSTS and FORCE_HTTPS to harden external traffic.
"""

import os
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
import logging
from app.routes.time_entries import router as time_entries_router
from app.routes.auth import router as auth_router
from app.routes import projects as projects_routes
from app.core.database import Base, engine

# Strict security middleware for production hardening
from starlette.middleware.httpsredirect import HTTPSRedirectMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

APP_ENVIRONMENT = os.getenv("APP_ENV", "dev").lower()

APP_NAME = os.getenv("APP_NAME", "Logger API")


# Parse BACKEND_CORS_ORIGINS from CSV or JSON array to a normalized list
_def_origins = ["http://localhost:5173", "http://127.0.0.1:5173"]
_env_origins = os.getenv("BACKEND_CORS_ORIGINS", "").strip()

log = logging.getLogger("uvicorn.error")


def _truthy(v: str | None) -> bool:
    return str(v or "").strip().lower() in {"1", "true"}


def _parse_origins(val: str):
    if not val:
        return []
    val = val.strip()
    if val.startswith("["):
        try:
            import json

            arr = json.loads(val)
            return [s.strip() for s in arr if isinstance(s, str) and s.strip()]
        except Exception:
            pass
    return [o.strip() for o in val.split(",") if o.strip()]


BACKEND_CORS_ORIGINS = _parse_origins(_env_origins) or _def_origins


# Instantiate the application; middlewares must be added immediately after this
app = FastAPI(title=APP_NAME)

# --- CORS must wrap all routes (place before routers & other middlewares) ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=BACKEND_CORS_ORIGINS,  # explicit list is required when credentials are used
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Enforce HTTPS and trusted hosts in production-like environments only.
# Locally (APP_ENV=dev), we keep HTTP to avoid 307 redirects on health checks and manual testing.
if APP_ENVIRONMENT == "prod" and _truthy(os.getenv("FORCE_HTTPS")):
    app.add_middleware(HTTPSRedirectMiddleware)

trusted_hosts = os.getenv("TRUSTED_HOSTS", "").split(",")
trusted_hosts = [h.strip() for h in trusted_hosts if h.strip()]
if trusted_hosts:
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=trusted_hosts)


# Lightweight observability: log 404s under /api/* with user-agent/referer/client for debugging
@app.middleware("http")
async def log_404s(request: Request, call_next):
    resp = await call_next(request)
    if request.url.path.startswith("/api/") and resp.status_code == 404:
        ua = request.headers.get("user-agent")
        ref = request.headers.get("referer")
        log.warning(
            f"[404] {request.method} {request.url.path} UA={ua} Ref={ref} Client={request.client}"
        )
    return resp


@app.on_event("startup")
def _startup():
    backend = "unknown"
    try:
        backend = engine.url.get_backend_name()
    except Exception:
        pass

    enabled = _truthy(os.getenv("CREATE_TABLES_ON_STARTUP")) or backend == "postgres"
    if enabled:
        log.info(f"[startup] create_all enabled (backend={backend})")
        Base.metadata.create_all(bind=engine)
    else:
        log.info(
            f"[startup] create_all skipped (backend={backend}); relying on Alembic migrations"
        )

    log.info(f"[startup] {APP_NAME} booted; CORS={BACKEND_CORS_ORIGINS}")


log.info(f"[startup] {APP_NAME} booted; CORS={BACKEND_CORS_ORIGINS}")

# Mount routers under /api/* paths
app.include_router(
    time_entries_router, prefix="/api/time-entries", tags=["time-entries"]
)
app.include_router(auth_router, prefix="/api/auth", tags=["auth"])
app.include_router(projects_routes.router, prefix="/api/projects", tags=["projects"])


# Small convenience endpoint for health checks
@app.get("/healthz")
def health_check():
    return {"status": "ok"}


# Root hint with docs & health pointers
@app.get("/", include_in_schema=False)
def root():
    # Small landing hint
    return {"service": APP_NAME, "docs": "/docs", "health": "/healthz"}
