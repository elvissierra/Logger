from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routes.time_entries import router as time_entries_router
from app.core.config import get_settings
from app.core.database import Base, engine

settings = get_settings()

app = FastAPI(title=settings.APP_NAME)

# CORS for the SPA (adjust origins via BACKEND_CORS_ORIGINS env)
app.add_middleware(
  CORSMiddleware,
  allow_origins=settings.BACKEND_CORS_ORIGINS,
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
    return {"service": settings.APP_NAME, "docs": "/docs", "health": "/healthz"}