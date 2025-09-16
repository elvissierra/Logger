

"""
Application settings (Knowledge Drop)

What this file does
- Central, dependency-light settings holder. Reads from environment at import time so processes (Uvicorn, Alembic) get consistent values.
- Exposes a tiny Settings object via get_settings() with LRU caching to avoid re-parsing env repeatedly.

How it collaborates
- main.py reads BACKEND_CORS_ORIGINS and installs CORSMiddleware accordingly.
- database.py consumes DATABASE_URL to build the SQLAlchemy engine.
- All route code can depend on get_settings() without having to import os/env repeatedly.

Why necessary
- Keeps configuration in one place; avoids circular imports between app startup modules.

Notes
- Keep types simple (str, List[str]) to avoid pulling in pydantic just for settings.
"""
import os
from functools import lru_cache
from typing import List


class Settings:
    # Human-readable service name; surfaced in docs/logs.
    APP_NAME: str = os.getenv("APP_NAME", "Logger API")

    # Primary DB connection string. Use Postgres in prod; SQLite file fallback for local dev/test.
    # Examples: "postgresql+psycopg://user:pass@host:5432/db" or "sqlite:///./logger.db"
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./logger.db")

    # Origins allowed by CORS. Parsed from CSV so it can be set as a simple env var.
    # main.py consumes this to install CORSMiddleware with credentials enabled.
    BACKEND_CORS_ORIGINS: List[str] = [
        origin.strip()
        for origin in os.getenv("BACKEND_CORS_ORIGINS", "http://localhost:5173").split(",")
        if origin.strip()
    ]

    # Default application timezone for presentation (not for DB storage which is UTC).
    TIMEZONE: str = os.getenv("TIMEZONE", "America/Chicago")


@lru_cache
def get_settings() -> Settings:
    return Settings()