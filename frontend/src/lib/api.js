// Shared API helpers for the Logger frontend
const rawBase = import.meta.env.VITE_API_BASE
// Treat an explicitly-set empty string as a valid value so we can use relative paths in prod
export const API_BASE = rawBase !== undefined
  ? rawBase
  : (import.meta.env.PROD ? '' : 'http://127.0.0.1:8000')

export function getCsrf () {
  const m = document.cookie.match(/(?:^|; )csrf_token=([^;]+)/)
  return m ? decodeURIComponent(m[1]) : ''
}

// fetch wrapper: includes credentials and refreshes on 401 (except for auth endpoints)
// If refresh fails, emit a global event so the app can redirect/clear state.
export async function apiFetch (url, opts = {}) {
  const req = () => fetch(url, { credentials: 'include', ...opts })

  const isAuthCall = typeof url === 'string' && (
    url.includes('/api/auth/me') ||
    url.includes('/api/auth/login') ||
    url.includes('/api/auth/register') ||
    url.includes('/api/auth/refresh') ||
    url.includes('/api/auth/logout')
  )

  let res = await req()
  if (res.status !== 401) return res

  // If we're calling an auth endpoint itself (especially /me on first load), don't try refresh.
  if (isAuthCall) {
    // Let the UI decide what to do with a 401 /me (typically show login).
    return res
  }

  // Attempt refresh once.
  let refreshed = false
  try {
    const r = await fetch(`${API_BASE}/api/auth/refresh`, { method: 'POST', credentials: 'include' })
    refreshed = r.ok
  } catch (_) {
    refreshed = false
  }

  if (refreshed) {
    // Retry the original request once.
    res = await req()
    return res
  }

  // Refresh failed; surface it to the UI so we can redirect/clear local state.
  try {
    window.dispatchEvent(new CustomEvent('logger:auth-expired'))
  } catch (_) {}

  return res
}

// Convenience helpers
export async function getJSON (path) {
  const r = await apiFetch(`${API_BASE}${path}`)
  if (!r.ok) throw new Error(await r.text())
  return r.json()
}

export async function postJSON (path, body, headers = {}) {
  const csrf = getCsrf()
  const finalHeaders = { 'Content-Type': 'application/json', ...headers }
  if (csrf) finalHeaders['X-CSRF-Token'] = csrf
  const r = await apiFetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: finalHeaders,
    body: JSON.stringify(body)
  })
  if (!r.ok) throw new Error(await r.text())
  return r.json()
}

export async function patchJSON (path, body, headers = {}) {
  const csrf = getCsrf()
  const finalHeaders = { 'Content-Type': 'application/json', ...headers }
  if (csrf) finalHeaders['X-CSRF-Token'] = csrf
  const r = await apiFetch(`${API_BASE}${path}`, {
    method: 'PATCH',
    headers: finalHeaders,
    body: JSON.stringify(body)
  })
  if (!r.ok) throw new Error(await r.text())
  return r.json()
}

export async function del (path, headers = {}) {
  const csrf = getCsrf()
  const finalHeaders = { ...headers }
  if (csrf) finalHeaders['X-CSRF-Token'] = csrf
  const r = await apiFetch(`${API_BASE}${path}`, { method: 'DELETE', headers: finalHeaders })
  if (!r.ok) throw new Error(await r.text())
  return true
}

// Subscribe helper for auth-expired (logout/redirect).
export function onAuthExpired (handler) {
  const fn = () => handler?.()
  window.addEventListener('logger:auth-expired', fn)
  return () => window.removeEventListener('logger:auth-expired', fn)
}