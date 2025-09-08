import os
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
import logging
from app.routes.time_entries import router as time_entries_router
from app.routes.auth import router as auth_router
from app.core.database import Base, engine
# Strict security middleware for production hardening
from starlette.middleware.httpsredirect import HTTPSRedirectMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware as StarletteCORS  # alias not used but avoids confusion

APP_NAME = os.getenv("APP_NAME", "Logger API")

# CORS origins: comma-separated env var or default to Vite dev server
_origins_env = os.getenv("BACKEND_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
BACKEND_CORS_ORIGINS = [o.strip() for o in _origins_env.split(",") if o.strip()]

app = FastAPI(title=APP_NAME)

# Enforce HTTPS and trusted hosts in production
if os.getenv("FORCE_HTTPS", "0") == "1":
    app.add_middleware(HTTPSRedirectMiddleware)
trusted_hosts = os.getenv("TRUSTED_HOSTS", "").split(",")
trusted_hosts = [h.strip() for h in trusted_hosts if h.strip()]
if trusted_hosts:
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=trusted_hosts)

log = logging.getLogger("uvicorn.error")

@app.middleware("http")
async def log_404s(request: Request, call_next):
    resp = await call_next(request)
    if request.url.path.startswith("/api/") and resp.status_code == 404:
        ua = request.headers.get("user-agent")
        ref = request.headers.get("referer")
        log.warning(f"[404] {request.method} {request.url.path} UA={ua} Ref={ref} Client={request.client}")
    return resp

app.add_middleware(
    CORSMiddleware,
    allow_origins=BACKEND_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create tables in dev if using SQLite fallback (safe no-op for Postgres)
@app.on_event("startup")
def _startup():
    Base.metadata.create_all(bind=engine)

log.info(f"[startup] {APP_NAME} booted; CORS={BACKEND_CORS_ORIGINS}")
# Routers
app.include_router(time_entries_router, prefix="/api/time-entries", tags=["time-entries"])
app.include_router(auth_router,         prefix="/api/auth",         tags=["auth"])

@app.get("/healthz")
def health_check():
    return {"status": "ok"}

@app.get("/", include_in_schema=False)
def root():
    # Small landing hint
    return {"service": APP_NAME, "docs": "/docs", "health": "/healthz"}