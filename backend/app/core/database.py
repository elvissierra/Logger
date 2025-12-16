"""
Database bootstrap (Knowledge Drop)

What this file does
- Loads environment (.env if present) and constructs the SQLAlchemy Engine + Session factory.
- Exposes the declarative Base for models and a get_db() dependency for FastAPI routes.

How it collaborates
- CRUD modules receive a Session via get_db(); Alembic imports Base.metadata for migrations.
- main.py should import get_db for dependencies, never import SessionLocal directly in routes.

Why necessary
- Centralizes engine creation, connection args (SQLite special case), and lifetime management.

Notes
- pool_pre_ping=True avoids stale-connection errors after idle periods.
- SQLite needs check_same_thread=False to allow use in FastAPI workers; Postgres does not.
"""

import os
from pathlib import Path
from dotenv import load_dotenv, find_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

"""
# Load env early so DATABASE_URL is available in dev shells and Alembic.
# load_dotenv(find_dotenv(...)) looks upward from CWD; the second call loads app/.env when running from project root.
"""
load_dotenv(find_dotenv(usecwd=True), override=False)
load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL must be set (e.g. postgresql+psycopg://user:pass@host:5432/dbname)"
    )

is_sqlite = DATABASE_URL.lower().startswith("sqlite")
connect_args = {"check_same_thread": False} if is_sqlite else {}
"""
# Engine & session factory
# - future=True enables SQLAlchemy 2.0 style APIs
# - pool_pre_ping avoids stale connections on long-lived processes
# - connect_args only applied for SQLite
"""
engine = create_engine(
    DATABASE_URL,
    future=True,
    pool_pre_ping=True,
    connect_args=connect_args,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

# Declarative base for models
Base = declarative_base()


# FastAPI dependency
def get_db():
    """FastAPI dependency that yields a short-lived Session and guarantees close() on exit."""
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
