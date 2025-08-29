

"""
Application settings.
Keep this simple and dependency-light (no extra packages needed).
"""
import os
from functools import lru_cache
from typing import List


class Settings:
    APP_NAME: str = os.getenv("APP_NAME", "Logger API")
    # Use Postgres in prod; for local dev fallback to SQLite file
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./logger.db")
    # Comma-separated list of origins, e.g. "http://localhost:5173,https://app.example.com"
    BACKEND_CORS_ORIGINS: List[str] = [
        origin.strip()
        for origin in os.getenv("BACKEND_CORS_ORIGINS", "http://localhost:5173").split(",")
        if origin.strip()
    ]
    TIMEZONE: str = os.getenv("TIMEZONE", "America/Chicago")


@lru_cache
def get_settings() -> Settings:
    return Settings()