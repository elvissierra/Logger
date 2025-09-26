# Docker in the Logger Project

This guide explains **how Docker works** and **why we use it** in this repo. It also shows how the three services (API, DB, Frontend) run together via **docker-compose** and what to do when something goes wrong.

---

## 1) What is Docker (in 60 seconds)?
- A **container** is a lightweight, isolated environment that runs your app with its exact runtime + dependencies.
- An **image** is a read-only template built from a `Dockerfile` (like a snapshot of your app + deps).
- A **container** is a running instance of an image (like a process with strong isolation).
- **Compose** describes how multiple containers run together (networking, env vars, volumes).

### Containers vs VMs
- **VMs** include a full guest OS and virtualized hardware → heavier.
- **Containers** share the host kernel and package only what you need → lighter, faster start, smaller.

**Why we care:** the same image runs the same way in dev, CI, and prod → no “works on my machine.”

---

## 2) How Logger uses Docker

We have three services defined in [`docker-compose.yml`](./docker-compose.yml):

1. **API** (`backend/Dockerfile`)
   - Base: `python:3.11-slim`
   - Installs system deps (e.g., `libpq-dev`) and Python deps from `backend/requirements.txt`
   - Runs Alembic migrations if `backend/alembic.ini` exists
   - Starts Uvicorn: `uvicorn main:app --host 0.0.0.0 --port 8000`
   - Healthcheck: `GET /healthz`

2. **DB** (`postgres:16-alpine`)
   - Initializes a `logger` database
   - Persists data in the **named volume** `pgdata`
   - Healthcheck: `pg_isready` against the `logger` DB

3. **Frontend** (`frontend/Dockerfile`)
   - `node:20-alpine` builds the Vue app → Nginx serves the static site
   - History fallback in Nginx so SPA routes work

Compose wires them together on a private network and exposes ports:
- Frontend → host **8080**
- API → host **8000**
- DB → host **5432** (only for local tools; the API uses the compose network name `db`)

---

## 3) Files to know

- [`backend/Dockerfile`](./backend/Dockerfile)
  - Copies backend code into `/app/backend`
  - Runs Alembic migrations (if present), then starts Uvicorn
- [`frontend/Dockerfile`](./frontend/Dockerfile)
  - Builds the SPA and serves via Nginx
- [`docker-compose.yml`](./docker-compose.yml)
  - Orchestrates API, DB, Frontend
  - Passes important env vars to the API (CORS, cookies, secrets, timezone)

> Tip: Add a root `.dockerignore` to keep images small:
> ```
> **/__pycache__/
> **/.pytest_cache/
> **/.venv/
> **/node_modules/
> **/dist/
> .git
> .DS_Store
> ```

---

## 4) Dev commands (local, via Compose)

```bash
# Build everything
docker compose build

# Start everything in the background
docker compose up -d

# Follow backend logs (Ctrl+C to stop tailing)
docker compose logs -f api

# Stop and remove containers, keep DB volume
docker compose down

# Clean slate (remove containers + volumes)
docker compose down -v
```

Health checks:
```bash
curl -i http://localhost:8000/healthz      # API should return 200
open http://localhost:8080                 # Frontend
```

Shells into containers:
```bash
docker compose exec api bash
psql -h localhost -p 5432 -U postgres -d logger   # from host
```

Rebuild after changing Python deps or Dockerfiles:
```bash
docker compose build --no-cache api
```

---

## 5) How the pieces talk to each other

- **Networking**: Compose creates an isolated network. Services are reachable by name (e.g., the API connects to Postgres at `db:5432`).
- **Environment**: The API gets configuration from `docker-compose.yml` (**do not** hardcode secrets in code). In dev we use safe defaults.
- **Volumes**: The DB uses a named volume (`pgdata`) so data persists across container restarts.
- **Entrypoint**: The API container runs an entry script that first applies migrations (`alembic upgrade head`) then starts Uvicorn.

---

## 6) Important environment variables

From `docker-compose.yml` under `api`:

- `DATABASE_URL=postgresql+psycopg://postgres:postgres@db:5432/logger`
- `BACKEND_CORS_ORIGINS=http://localhost:8080,http://127.0.0.1:8080`  
  Allow both hostnames to avoid CORS issues in dev.
- `SECRET_KEY=change-me-in-prod`  
  Rotate this in production (use a secret manager or env var).
- `ACCESS_TOKEN_MIN=10` / `REFRESH_TOKEN_DAYS=14`
- `COOKIE_SECURE=0`, `COOKIE_DOMAIN=localhost`  
  Dev-only cookie settings; in prod use `COOKIE_SECURE=1` and your real domain.
- `TIMEZONE=America/Chicago`

**Frontend → API base**: When running Vite (not Docker), set `frontend/.env.local`:
```
VITE_API_BASE=http://localhost:8000
```

---

## 7) Common troubleshooting

- **401s (Unauthorized) on `/api/auth/me` or `/api/auth/refresh`**
  - Ensure the frontend points to **http://localhost:8000** (not 127.0.0.1) so cookies match `COOKIE_DOMAIN=localhost`.
  - Clear cookies for both hosts if you recently changed hosts.
  - Confirm `BACKEND_CORS_ORIGINS` includes both `http://localhost:8080` and `http://127.0.0.1:8080`.

- **API can’t reach DB**
  - Check `DATABASE_URL` host is `db` (compose service name) and the `db` container is healthy.
  - `docker compose ps` → confirm both services are healthy.

- **Migrations didn’t run**
  - Ensure `backend/alembic.ini` exists inside the image and your Alembic env is configured.
  - Inspect logs: `docker compose logs -f api`.

- **Rebuilding doesn’t reflect changes**
  - Use `--no-cache` on the service that changed, or `docker compose up -d --build`.

---

## 8) Why this design

- **Consistency:** same containers in dev/staging/prod.
- **Isolation:** each service keeps its own deps.
- **Simplicity:** one compose file spins up the whole stack.
- **Observability:** healthchecks make dependencies explicit (DB → API → Frontend).

---

## 9) Moving toward deployment

- Push images to a registry (GHCR, Docker Hub) via CI.
- Use a runtime:
  - **Single VM** (Docker + Compose)
  - **Fly.io / Render / Railway** (containers as-a-service)
  - **Kubernetes** (if/when you need it)
- Configure domain, TLS, and production cookie/security settings.

> See the next doc for deployment options.

---

## 10) Diagrams: how to visualize this stack

You can think of the Logger stack as three containers on one private network. Here’s a simple Mermaid diagram you can paste into docs that support it (e.g., GitHub, some wikis):

```mermaid
flowchart LR
  subgraph compose_network[Docker Compose Network]
    FE[Frontend (Nginx)] -- HTTP :80 → API
    API[API (Uvicorn/FastAPI)] -- TCP :5432 → DB
    FE -. Browser HTTP :8080 .->|Host Port| FE
    API -. Host Port :8000 .-> API
    DB[(Postgres)]
  end
```

**Reading it:**
- The **browser** hits `http://localhost:8080` → forwarded to **Frontend** container port `80`.
- Frontend serves static files and calls the **API** at `http://localhost:8000` (host port → API container `8000`).
- The **API** connects to **DB** over the compose network using the service name `db:5432`.

**Tips for using diagrams:**
- **GitHub** renders Mermaid in Markdown by default. Keep the triple-fenced block with `mermaid` as shown above.
- If your editor does **not** render Mermaid, you can:
  - Install a Mermaid extension/preview plugin, **or**
  - Export the diagram to SVG/PNG using the Mermaid CLI and commit the image.
- Keep diagrams **close to the code** they describe (this file or a `docs/` folder) so they evolve with the system.
- Prefer simple high‑level diagrams over detailed ones; networks and ports often change during development.

**Exporting a diagram (CLI example):**
If your editor doesn’t render Mermaid, you can generate an image via the CLI and commit it:

```bash
# install once (Node required)
npm i -g @mermaid-js/mermaid-cli

# save the diagram from this README into diagram.mmd, then render PNG/SVG
mmdc -i diagram.mmd -o diagram.png
mmdc -i diagram.mmd -o diagram.svg
```

> If your editor doesn’t render Mermaid, keep an ASCII note in the repo describing the same flow.

---

## 11) Resource sizing tips (dev)

Containers are light, but they still consume CPU/RAM. For local development:

- **Docker Desktop settings**: Set a reasonable limit (e.g., 4 CPUs / 6–8 GB RAM) globally. This prevents a runaway build from starving your machine.
- **Postgres**: The default `postgres:16-alpine` settings are conservative and fine for dev. If you bulk-load data, consider giving Docker Desktop more RAM while importing.
- **API (Uvicorn)**: In dev we run a single worker with `--reload`. That’s best for hot-reload; multiple workers aren’t necessary locally.
- **Frontend (Nginx)**: Static serving is tiny; almost no tuning needed.

If you really need to constrain a dev container, prefer global limits via Docker Desktop. The `deploy.resources` block in `docker-compose.yml` is intended for **Swarm/Kubernetes** and is generally **ignored by plain Compose**. If you must set per-container limits with classic Compose, you can run those services with `docker run --cpus/--memory` manually or use a separate Swarm/K8s manifest for production.

**Clarifications:**
- Compose (non‑Swarm) **ignores** `deploy.resources`. Use Docker Desktop global limits or run containers with explicit `--cpus/--memory` flags if testing constraints.
- CPU spikes during `npm ci`/`pip install` and image builds are normal; they happen **once** per cache layer. Subsequent builds are much faster.
- On Apple Silicon, some base images may use emulation for x86 layers; prefer `*-alpine` or `linux/arm64` when available.

**Where to set limits (Docker Desktop):**
- **macOS**: Docker Desktop → Settings → Resources → set CPUs & Memory → **Apply & Restart**.
- **Windows**: Docker Desktop → Settings → Resources → set CPUs & Memory → **Apply & Restart**.
- **Ad‑hoc test** for one service (not permanent):
  ```bash
  docker compose run --rm --service-ports \
    --cpus="2" --memory="2g" api \
    uvicorn main:app --host 0.0.0.0 --port 8000
  ```
---

## 12) Attaching a debugger to the API container (VS Code / debugpy)

There are two common approaches:

### A) Quick attach with VS Code Docker extension (no code changes)
1. Install the **Docker** and **Python** extensions in VS Code.
2. `Docker: Containers` → right-click the `api` container → **Attach Shell** to verify paths.
3. Use **Run and Debug** → **Python: Attach using Process** → select the `uvicorn` process in the container. (If this doesn’t show, use method B.)

### B) Use `debugpy` inside the container (reliable)
1. Ensure `debugpy` is installed in the backend image. If it’s not in your `requirements.txt`, you can add it or install at runtime:
   ```bash
   docker compose exec api pip install debugpy
   ```
2. Start `uvicorn` under `debugpy` (one-time test):
   ```bash
   docker compose exec api bash -lc "python -m debugpy --wait-for-client --listen 0.0.0.0:5678 -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload"
   ```
   - The API will block until a debugger attaches on **:5678**.
3. In VS Code, create a **launch.json** and attach to port 5678:
   ```json
   {
     "version": "0.2.0",
     "configurations": [
       {
         "name": "Attach to API (debugpy in container)",
         "type": "python",
         "request": "attach",
         "connect": { "host": "localhost", "port": 5678 },
         "pathMappings": [
           { "localRoot": "${workspaceFolder}/backend", "remoteRoot": "/app/backend" }
         ]
       }
     ]
   }
   ```
4. Set breakpoints in your backend code (e.g., routes) and hit the API.

#### Optional: make debugpy the default in dev
If you prefer not to run long shell commands, you can temporarily override the API command:
```bash
docker compose stop api
# One-off debug run (foreground)
docker compose run --service-ports --rm api \
  python -m debugpy --wait-for-client --listen 0.0.0.0:5678 \
  -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```
> `--service-ports` exposes the container ports from compose so VS Code can attach.

**Notes:**
- Keep `pathMappings` accurate so debugger file paths line up (`/app/backend` inside container ↔ `backend/` on your host).
- Don’t include debugpy in production images; it’s for dev only.

**Troubleshooting debugger attach:**
- If VS Code cannot attach, confirm the port is open: `docker compose exec api ss -ltnp | grep 5678`.
- Firewalls/VPNs can block local ports; try disabling them temporarily or use a different port.
- Ensure `pathMappings` match: `/app/backend` **inside** the container must map to your local `backend/` folder so breakpoints bind.
- If `--reload` restarts Uvicorn too quickly for the debugger to connect, remove `--reload` for the session or set `--reload-delay 0.5`.

**Optional: VS Code task for quick debug run**
Add to `.vscode/tasks.json`:
```json
{
  "version": "2.0.0",
  "tasks": [
    {
      "label": "Run API with debugpy (compose)",
      "type": "shell",
      "command": "docker compose run --service-ports --rm api python -m debugpy --wait-for-client --listen 0.0.0.0:5678 -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload",
      "problemMatcher": []
    }
  ]
}
```
Then **Run Task… → Run API with debugpy (compose)**, and attach with the launch config shown above.
---
