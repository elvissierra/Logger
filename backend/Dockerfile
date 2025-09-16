version: "3.9"

services:
  api:
    build:
      context:
      dockerfile: backend/Dockerfile
    environment:
      - DATABASE_URL=postgresql+psycopg://postgres:postgres@db:5432/logger
      - BACKEND_CORS_ORIGINS=http://localhost:8080
      - SECRET_KEY=change-me-in-prod
      - ACCESS_TOKEN_MIN=10
      - REFRESH_TOKEN_DAYS=14
      - COOKIE_SECURE=0
      - TIMEZONE=America/Chicago
    ports:
      - "8000:8000"
    depends_on:
      db:
        condition: service_healthy
    healthcheck:
      test: ["CMD-SHELL", "curl -fsS http://localhost:8000/healthz || exit 1"]
      interval: 10s
      timeout: 3s
      retries: 10
      start_period: 10s

  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
      POSTGRES_DB: logger
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres -d logger"]
      interval: 10s
      timeout: 5s
      retries: 10
      start_period: 10s

  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
    ports:
      - "8080:80"
    depends_on:
      api:
        condition: service_healthy

volumes:
  pgdata:
