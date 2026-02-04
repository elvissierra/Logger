# ---- Backend Dockerfile (FastAPI + Uvicorn) ----
FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# System deps for building wheels & psycopg (libpq)
RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential libpq-dev curl \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first (better layer caching)
COPY backend/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Copy backend source
COPY backend /app/backend

# Make project importable
ENV PYTHONPATH=/app/backend

# Minimal entrypoint with optional Alembic migration
RUN cat >/entrypoint.sh <<'EOF' \
 && chmod +x /entrypoint.sh
#!/usr/bin/env bash
set -euo pipefail

cd /app/backend

# Run migrations if Alembic config exists
if [ -f "/app/backend/alembic.ini" ]; then
  echo "[entrypoint] Running alembic upgrade head..."
  alembic upgrade head || echo "[entrypoint] Alembic skipped or failed (continuing)"
fi

echo "[entrypoint] Starting Uvicorn..."
exec uvicorn main:app --host 0.0.0.0 --port 8000
EOF

EXPOSE 8000

CMD ["/entrypoint.sh"]