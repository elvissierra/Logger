"""
SQLAlchemy database bootstrap (env-driven, no external config import).
"""
import os
from pathlib import Path
from dotenv import load_dotenv, find_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

load_dotenv(find_dotenv(usecwd=True), override=False)
load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)

# DATABASE_URL examples:
#   sqlite:///./app.db
#   postgresql+psycopg://user:pass@localhost:5432/logger
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL must be set (e.g. postgresql+psycopg://user:pass@host:5432/dbname)")

is_sqlite = DATABASE_URL.lower().startswith("sqlite")
connect_args = {"check_same_thread": False} if is_sqlite else {}
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
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()