from logging.config import fileConfig
import os

from sqlalchemy import engine_from_config, pool
from alembic import context

# Lightweight fallback loader so Alembic can read app/.env when running from CLI
def _fallback_database_url_from_dotenv() -> str | None:
    # Resolve .../app/migrations/env.py -> .../app/.env
    here = os.path.abspath(os.path.dirname(__file__))
    env_path = os.path.abspath(os.path.join(here, "..", ".env"))
    if not os.path.exists(env_path):
        return None
    try:
        with open(env_path, "r", encoding="utf-8") as fh:
            for raw in fh:
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("DATABASE_URL"):
                    _, val = line.split("=", 1)
                    val = val.strip().strip('"').strip("'")
                    return val
    except Exception:
        return None
    return None

# --- Import your SQLAlchemy Base + models so Alembic "sees" them
from app.core.database import Base
# Ensure model modules are imported to register tables/indexes on Base.metadata
from app.models import time_entry  # noqa: F401  (import side-effect registers model)

# this is the Alembic Config object
config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Provide metadata to Alembic's autogenerate
target_metadata = Base.metadata

def get_url() -> str:
    # Prefer environment variable so CI/CD and shells can override
    url = os.getenv("DATABASE_URL")
    if url:
        return url
    # Fallback to app/.env for local developer convenience
    url = _fallback_database_url_from_dotenv()
    if url:
        return url
    raise RuntimeError("DATABASE_URL is not set")

def run_migrations_offline():
    """Run migrations in 'offline' mode."""
    context.configure(
        url=get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,             # detect type changes
        compare_server_default=True,   # detect default changes
    )
    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online():
    """Run migrations in 'online' mode."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        url=get_url(),
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )
        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()