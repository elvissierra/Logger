import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routes.time_entries import router as time_entries_router
from app.core.database import Base, engine

APP_NAME = os.getenv("APP_NAME", "Logger API")

# CORS origins: comma-separated env var or default to Vite dev server
_origins_env = os.getenv("BACKEND_CORS_ORIGINS", "http://localhost:5173")
BACKEND_CORS_ORIGINS = [o.strip() for o in _origins_env.split(",") if o.strip()]

app = FastAPI(title=APP_NAME)

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

# Routers
app.include_router(time_entries_router, prefix="/api/time-entries", tags=["time-entries"])

@app.get("/healthz")
def health_check():
    return {"status": "ok"}

@app.get("/", include_in_schema=False)
def root():
    # Small landing hint
    return {"service": APP_NAME, "docs": "/docs", "health": "/healthz"}