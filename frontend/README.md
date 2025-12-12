# Vue 3 + Vite

This template should help get you started developing with Vue 3 in Vite. The template uses Vue 3 `<script setup>` SFCs, check out the [script setup docs](https://v3.vuejs.org/api/sfc-script-setup.html#sfc-script-setup) to learn more.

Learn more about IDE Support for Vue in the [Vue Docs Scaling up Guide](https://vuejs.org/guide/scaling-up/tooling.html#ide-support).

# Logger Frontend — Vue 3 + Vite

This is the SPA frontend for the **Logger** time‑tracking app. It talks to the FastAPI
backend via JSON APIs and uses cookie‑based auth (`access_token` / `refresh_token`
+ `csrf_token`) with `fetch(..., { credentials: 'include' })`.

The stack:

- Vue 3 + Vite
- Script setup SFCs
- Shared API helpers in `src/lib/api.js` (handles cookies + refresh on 401)
- Tailored for a FastAPI backend at `/api/*`

---

## Quickstart (local dev)

1. Install dependencies:

```bash
cd frontend
npm install
```

2. Create a `.env` file based on `.env.example`:

```env
# FastAPI backend running on :8000
VITE_API_BASE=http://localhost:8000
```

3. Start the dev server:

```bash
npm run dev
```

- Frontend: http://localhost:5173
- Backend (from the backend README): http://localhost:8000

With this setup, `src/lib/api.js` will call `http://localhost:8000/api/...` and send
cookies using `credentials: 'include'`.

---

## API helper behavior

The key helpers live in `src/lib/api.js`:

- `API_BASE` — derived from `VITE_API_BASE`. If `VITE_API_BASE` is **unset**, it
  falls back to `http://127.0.0.1:8000` for dev.
- `apiFetch(url, opts)` — wraps `fetch` with `credentials: 'include'` and
  transparently calls `/api/auth/refresh` once if a request returns `401`.
- `getJSON`, `postJSON`, `patchJSON`, `del` — convenience helpers that:
  - prepend `API_BASE` to paths like `/api/time-entries/`
  - attach `X-CSRF-Token` when a `csrf_token` cookie is present
  - throw on non‑OK responses.

The `Login` view uses `postJSON` to hit `/api/auth/login` and then relies on the
backend to set `access_token` / `refresh_token` / `csrf_token` cookies. Subsequent
requests automatically send those cookies.

---

## Render / production deployment

In Render, the recommended layout is:

- **Static Site**: hosts the built frontend (e.g. `https://logger-ui-…onrender.com`)
- **Web Service**: FastAPI backend (e.g. `https://logger-…onrender.com`)
- **Rewrite rule** on the Static Site:

  - Source: `/api/*`
  - Destination: `https://<your-backend-service>.onrender.com/api/*`
  - Action: `Rewrite`

In the Static Site’s environment, set:

```env
VITE_API_BASE=
```

so that the SPA issues same‑origin requests like `/api/auth/login`. Render rewrites
those to the backend. Cookies are then first‑party to the frontend host, which
keeps auth stable across refreshes.

---

## Troubleshooting

- **401 "Missing access token" on `/api/auth/me`**  
  Usually means no `access_token` cookie was sent. Check:
  - Cookies are present for the frontend origin in DevTools → Application → Cookies.
  - Requests are going through `apiFetch` (with `credentials: 'include'`).
  - In production, `VITE_API_BASE` is empty and the `/api/*` rewrite is configured.

- **CORS errors**  
  Ensure the backend `BACKEND_CORS_ORIGINS` includes the frontend origin
  (e.g. `http://localhost:5173` for dev or `https://logger-ui-…onrender.com` in prod).

For backend details, see `../backend/README.md`.