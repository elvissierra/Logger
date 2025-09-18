// Shared API helpers for the Logger frontend
export const API_BASE = import.meta.env.VITE_API_BASE || 'http://127.0.0.1:8000'

export function getCsrf () {
  const m = document.cookie.match(/(?:^|; )csrf_token=([^;]+)/)
  return m ? decodeURIComponent(m[1]) : ''
}

// fetch wrapper: includes credentials and silently refreshes on 401
export async function apiFetch (url, opts = {}) {
  const req = () => fetch(url, { credentials: 'include', ...opts })
  let res = await req()
  if (res.status === 401) {
    try {
      const r = await fetch(`${API_BASE}/api/auth/refresh`, { method: 'POST', credentials: 'include' })
      if (r.ok) res = await req()
    } catch (_) {}
  }
  return res
}

// Convenience helpers
export async function getJSON (path) {
  const r = await apiFetch(`${API_BASE}${path}`)
  if (!r.ok) throw new Error(await r.text())
  return r.json()
}
export async function postJSON (path, body, headers = {}) {
  const r = await apiFetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...headers },
    body: JSON.stringify(body)
  })
  if (!r.ok) throw new Error(await r.text())
  return r.json()
}
export async function patchJSON (path, body, headers = {}) {
  const r = await apiFetch(`${API_BASE}${path}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json', ...headers },
    body: JSON.stringify(body)
  })
  if (!r.ok) throw new Error(await r.text())
  return r.json()
}
export async function del (path, headers = {}) {
  const r = await apiFetch(`${API_BASE}${path}`, { method: 'DELETE', headers })
  if (!r.ok) throw new Error(await r.text())
  return true
}