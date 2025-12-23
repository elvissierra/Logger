<script setup>
/**
 * Knowledge Drop — TimeBoard.vue (primary UI)
 *
 * Overall purpose
 * - This is the main authenticated UI for tracking time. It fetches a week's worth of entries,
 *   groups them into swimlanes (by project or activity), and renders two layouts:
 *   (1) Board/Grid with a weekly matrix and a Today focus area, (2) Simple layout with per-day columns.
 *
 * How pieces work together
 * - Auth: App.vue handles login/logout and sets the user id in localStorage; this component assumes the user is already authenticated.
 * - API access: apiFetch() wraps fetch with credentials and silent refresh on 401 via /api/auth/refresh.
 * - Timers: startTimer()/stopTimer() create/extend entries; runningId is persisted per-user in localStorage.
 * - Mapping: assignCardsToGrid() places entries into lanes and day columns; drag & drop updates times and grouping.
 * - State: groupBy controls columns vs swimlanes; layoutMode toggles between grid and simple presentations.
 * - Local-only meta: lane descriptions & priority live in localStorage (no backend schema required yet).
 *
 * Why necessary
 * - Keeps the UX responsive (local reorder, meta, and layout state) while persisting the source of truth on the server.
 * - Encapsulates week navigation and aggregation logic so cards can be rendered consistently across layouts.
 *
 * Notes
 * - All date math is in local time for UI; we convert to UTC ISO when persisting (composeISOFromLaneAndTime).
 * - 15‑minute rounding is applied for user inputs and when moving cards across days.
 * - Be careful when changing storage keys (they include group/week so per-cell order persists correctly).
 */
import { ref, onMounted, onUnmounted, computed, watch } from 'vue'
import TimeCard from './TimeCard.vue'
import TodayLog from './TodayLog.vue'
import WeekLog from './WeekLog.vue'
import { API_BASE, apiFetch, getCsrf } from '../lib/api'
import {
  pad, startOfWeek, addDays, dateKey, labelFor,
  timeHMFromISO, composeISOFromLaneAndTime, laneKeyFromISO,
  hoursBetweenRounded, roundHMToQuarter, roundDateToQuarter,
  fmtH,
} from '../lib/time'

// --- Projects (authoritative created_at for lane visibility) ---
const projects = ref([]) // [{ code, created_at, ... }]
const projectMap = computed(() => Object.fromEntries(projects.value.map(p => [p.code, p])))

async function loadProjects() {
  try {
    const r = await apiFetch(`${API_BASE}/api/projects/`)
    if (r.ok) projects.value = await r.json()
  } catch {}
}

function laneVisibleOnDayByProjects(laneKey, dayKey) {
  const p = projectMap.value[laneKey]
  if (!p || !p.created_at) return true
  const createdKey = dateKey(new Date(p.created_at))
  return dayKey >= createdKey
}

// Theme handling: sync <html data-theme> + localStorage so user’s choice persists across sessions
// --- Global ticking for live timers ---
// --- Theme (light/dark) toggle ---
const theme = ref(
  localStorage.getItem('logger.theme')
  || (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light')
)
watch(theme, (t) => {
  document.documentElement.setAttribute('data-theme', t)
  localStorage.setItem('logger.theme', t)
}, { immediate: true })
function toggleTheme(){ theme.value = theme.value === 'dark' ? 'light' : 'dark' }
// Live ticking: shared clock for cards to recompute durations for running timers without per-card intervals
const nowTick = ref(Date.now())
let _nowHandle = null
onMounted(() => {
  _nowHandle = setInterval(() => (nowTick.value = Date.now()), 1000)
})
onUnmounted(() => { if (_nowHandle) clearInterval(_nowHandle) })

// Return the currently-authenticated user's id (or null if not signed in)
function currentUserId () {
  return localStorage.getItem('logger.userId') || null
}
function runningKey () {
  const uid = currentUserId()
  return uid ? `logger.runningEntry:${uid}` : null
}
const _rk = runningKey()
const runningId = ref(_rk ? localStorage.getItem(_rk) : null)

// --- Time rounding / overlap policy ---
// User-configurable increment (minutes). Default: 15.
const incrementMinutes = ref(Number(localStorage.getItem('logger.incrementMinutes') || 15))

watch(incrementMinutes, (v) => {
  const n = Number(v)
  const safe = Number.isFinite(n) ? String(Math.min(60, Math.max(1, Math.round(n)))) : '15'
  localStorage.setItem('logger.incrementMinutes', safe)
}, { immediate: true })

function _normInc() {
  const n = Number(incrementMinutes.value)
  if (!Number.isFinite(n)) return 15
  return Math.min(60, Math.max(1, Math.round(n)))
}

function roundDateToIncrement(dt, mode = 'round') {
  const mins = _normInc()
  const step = mins * 60 * 1000
  const t = dt instanceof Date ? dt.getTime() : new Date(dt).getTime()
  const q = t / step
  const k = mode === 'ceil' ? Math.ceil(q) : mode === 'floor' ? Math.floor(q) : Math.round(q)
  return new Date(k * step)
}

function roundHMToIncrement(hm, mode = 'round') {
  // hm: "HH:MM" in 24h
  const mins = _normInc()
  const parts = String(hm || '').split(':')
  const h = Number(parts[0] || 0)
  const m = Number(parts[1] || 0)
  const total = (h * 60) + m
  const q = total / mins
  const k = mode === 'ceil' ? Math.ceil(q) : mode === 'floor' ? Math.floor(q) : Math.round(q)
  const rounded = k * mins
  const hh = pad(Math.floor(rounded / 60) % 24)
  const mm = pad(rounded % 60)
  return `${hh}:${mm}`
}

const TARGET_WEEKLY_HOURS = 40



// Per-user running timer pointer: saved under key logger.runningEntry:<userId> so multiple users on the same browser
// don’t clash. We clear the key on stop or when navigating to a week where the entry is not present.
// --- Running timer pointer (client-side) ---
function setRunningId (id) {
  const v = (id === null || id === undefined || id === '') ? null : String(id)
  runningId.value = v
  const rk = runningKey()
  if (!rk) return
  if (v) localStorage.setItem(rk, v)
  else localStorage.removeItem(rk)
}
async function stopRunningIfAny () {
  if (!runningId.value) return { stopped: false, id: null, error: null, stoppedAtIso: null }

  const id = runningId.value
  try {
    const roundedStop = roundDateToIncrement(new Date(), 'ceil')
    const res = await apiFetch(`${API_BASE}/api/time-entries/${id}`, {
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRF-Token': getCsrf()
      },
      body: JSON.stringify({ end_utc: roundedStop.toISOString() })
    })

    if (!res.ok) {
      const msg = await extractErrorMessage(res)
      const status = res.status
      const lower = String(msg || '').toLowerCase()

      // If the backend indicates the entry is already stopped or no longer exists,
      // clear the local pointer and allow the user to start a new entry.
      if (
        status === 404 ||
        lower.includes('not found') ||
        lower.includes('already') ||
        lower.includes('stopped') ||
        lower.includes('ended') ||
        lower.includes('end_utc')
      ) {
        // Stale local pointer (e.g., entry already ended elsewhere). Clear it and proceed.
        setRunningId(null)
        await load()
      
        // Small debug breadcrumb without spamming.
        const now = Date.now()
        if (now - _stalePointerToastAt > 15000) {
          _stalePointerToastAt = now
          notify('Cleared stale running entry pointer (server already ended it).', 'info', 3200)
        }
      
        return { stopped: false, id, error: null, stoppedAtIso: null }
      }

      notify(`Could not stop existing timer: ${msg}`, 'error', 6000)
      return { stopped: false, id, error: msg, stoppedAtIso: null }
    }

    const stoppedAtIso = roundedStop.toISOString()
    setRunningId(null)
    await load()
    return { stopped: true, id, error: null, stoppedAtIso }
  } catch (e) {
    const msg = e?.message || String(e)
    notify(`Could not stop existing timer: ${msg}`, 'error', 6000)
    return { stopped: false, id, error: msg, stoppedAtIso: null }
  }
}
// Start a timer: stop any existing one, create a new *running* entry (end_utc=null).
async function startTimer (seedCard) {
  const { error, stoppedAtIso } = await stopRunningIfAny()
  if (error) {
    // Backend still thinks a timer is running; don’t try to start another.
    return
  }

  // If we stopped a previous timer, start the new one at the same rounded boundary.
  // Otherwise start at a rounded "now" boundary.
  const startIso = stoppedAtIso || roundDateToIncrement(new Date(), 'ceil').toISOString()

  const payload = {
    project_code: seedCard.project_code || seedCard.projectCode || '',
    activity: seedCard.activity || '',
    job_title: seedCard.job_title || seedCard.jobTitle || null,
    start_utc: startIso,
    end_utc: null,
    notes: `[prio:${(seedCard.priority || 'Normal').toLowerCase()}]` + (seedCard.notes ? ` ${seedCard.notes}` : '')
  }

  const res = await apiFetch(`${API_BASE}/api/time-entries/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': getCsrf() },
    body: JSON.stringify(payload)
  })
  if (!res.ok) {
    const msg = await extractErrorMessage(res)
    return notify(`Failed to start timer: ${msg}`, 'error', 6000)
  }

  const created = await res.json()
  setRunningId(created.id)
  await load()
  notify('Timer started', 'success')
}
async function stopTimer () {
  const { stopped } = await stopRunningIfAny()
  if (stopped) notify('Timer stopped', 'success')
}
function isLaneRunning(lane) {
  try {
    if (!runningId.value) return false
    for (const col of lane.columns) {
      if (col.cards && col.cards.some(x => String(x.id) === String(runningId.value))) return true
    }
    return false
  } catch { return false }
}

const runningLaneTitle = computed(() => {
  if (!runningId.value) return ''
  try {
    for (const lane of swimlanes.value) {
      for (const col of lane.columns) {
        if (col.cards && col.cards.some(c => String(c.id) === String(runningId.value))) {
          return lane.title
        }
      }
    }
    return ''
  } catch {
    return ''
  }
})

async function startLaneTimer(lane) {
  const meta = getLaneMeta(lane.key) || {}
  const seed = {
    project_code: groupBy.value === 'project_code' ? lane.title : '',
    projectCode:  groupBy.value === 'project_code' ? lane.title : '',
    activity:     groupBy.value === 'activity'     ? lane.title : '',
    priority: meta.priority || 'Normal',
    notes: ''
  }
  await startTimer(seed)
}

onMounted(async () => {
  await loadProjects()
  await load()
  window.addEventListener('keydown', onKey)
})
onUnmounted(() => window.removeEventListener('keydown', onKey))


// Lane metadata stored locally: description + priority per lane key. Useful before we add server-side project fields.
const PRIORITIES = ['Low','Normal','High','Critical']

function parsePriorityAndCleanNotes(notes) {
  if (!notes) return { priority: 'Normal', notes: '' }
  const m = notes.match(/^\s*\[prio:(low|normal|high|critical)\]\s*/i)
  if (m) {
    const p = m[1].toLowerCase()
    const pretty = p.charAt(0).toUpperCase() + p.slice(1)
    return { priority: pretty, notes: notes.replace(m[0], '') }
  }
  return { priority: 'Normal', notes }
}
function laneMetaStorageKey(laneKey) {
  const uid = currentUserId() || 'anon'
  return `logger.laneMeta:${uid}:${groupBy.value}:${laneKey}`
}
function getLaneMeta(laneKey) {
  try { return JSON.parse(localStorage.getItem(laneMetaStorageKey(laneKey)) || '{}') } catch { return {} }
}
function setLaneMeta(laneKey, meta) {
  localStorage.setItem(laneMetaStorageKey(laneKey), JSON.stringify(meta || {}))
}

// Inline lane meta editor state (replaces window.prompt UX)
const editingLaneKey = ref(null)
const laneMetaDraft = ref({ description: '', priority: 'Normal' })

function editLaneMeta(lane) {
  const current = getLaneMeta(lane.key)
  laneMetaDraft.value = {
    description: current.description || '',
    priority: current.priority || 'Normal'
  }
  editingLaneKey.value = lane.key
}

function cancelLaneMetaEdit() {
  editingLaneKey.value = null
}

function saveLaneMeta(lane) {
  const draft = laneMetaDraft.value || {}
  const rawPri = (draft.priority || 'Normal').trim()
  const validPri = PRIORITIES.includes(rawPri) ? rawPri : 'Normal'
  setLaneMeta(lane.key, {
    description: draft.description || '',
    priority: validPri
  })
  editingLaneKey.value = null
}

function isEditingLaneMeta(laneKey) {
  return editingLaneKey.value === laneKey
}
function laneDesc(key){ return (getLaneMeta(key).description || '') }
// ---- Week navigation ----
const currentWeekStart = ref(startOfWeek(new Date()))
const weekLabel = computed(() => {
  const mon = currentWeekStart.value
  const sun = addDays(mon, 6)
  const opts = { month: 'short', day: 'numeric' }
  return `${mon.toLocaleDateString(undefined, opts)} – ${sun.toLocaleDateString(undefined, opts)}`
})
const headerDays = computed(() => {
  const days = []
  for (let i = 0; i < 7; i++) {
    const d = addDays(currentWeekStart.value, i)
    days.push({ key: dateKey(d), date: d, label: labelFor(d) })
  }
  return days
})
function prevWeek() { currentWeekStart.value = addDays(currentWeekStart.value, -7) }
function nextWeek() { currentWeekStart.value = addDays(currentWeekStart.value, 7) }
function goToToday() { currentWeekStart.value = startOfWeek(new Date()) }

// ---- Grouping (columns) ----
// Grouping: controls how lanes are formed (projects vs activities). Changing this rebuilds the swimlanes.
const GROUPS = [
  { value: 'project_code', label: 'Project' },
  { value: 'activity', label: 'Activity' },
]
const groupBy = ref('project_code')

// --- Layout toggle (grid vs simple) ---
// Layout toggle: 'grid' (weekly board) vs 'simple' (per-day columns). Persisted so users return to their last choice.
const layoutMode = ref(localStorage.getItem('logger.layoutMode') || 'grid')
watch(layoutMode, (m) => localStorage.setItem('logger.layoutMode', m))

// Selected day for the simple layout (defaults to today within current week)
const selectedDayKey = ref('')
function colFor(lane, dayKey) {
  return lane.columns.find(c => c.dayKey === dayKey) || { dayKey, cards: [] }
}
watch([headerDays, currentWeekStart], () => {
  const keys = headerDays.value.map(d => d.key)
  if (!keys.length) return
  const todayK = dateKey(new Date())
  if (!keys.includes(selectedDayKey.value)) {
    selectedDayKey.value = keys.includes(todayK) ? todayK : keys[0]
  }
}, { immediate: true })

// ---- State ----
const swimlanes = ref([])
const loading = ref(false)
const error = ref('')

const toasts = ref([])
let _stalePointerToastAt = 0

function notify (msg, type = 'info', ttl = 3000) {
  const id = Math.random().toString(36).slice(2)
  toasts.value.push({ id, msg, type })
  setTimeout(() => {
    toasts.value = toasts.value.filter(t => t.id !== id)
  }, ttl)
}

// Try to extract a human-friendly error message from a fetch Response
async function extractErrorMessage (res) {
  if (!res) return 'Unknown error'
  try {
    const text = await res.text()
    if (!text) return `${res.status} ${res.statusText || 'Error'}`
    try {
      const data = JSON.parse(text)
      if (typeof data === 'string') return data
      if (data.detail) {
        return typeof data.detail === 'string'
          ? data.detail
          : JSON.stringify(data.detail)
      }
      if (data.message) return data.message
      return text
    } catch {
      return text
    }
  } catch {
    return `${res.status} ${res.statusText || 'Error'}`
  }
}

// DEV: Surface global errors as toasts
if (import.meta.env.DEV) {
  window.addEventListener('error', (e) => notify(`Error: ${e.error?.message || e.message}`, 'error', 6000))
  window.addEventListener('unhandledrejection', (e) => notify(`Unhandled: ${e.reason?.message || e.reason}`, 'error', 6000))
}
// --- shortcuts ---
function onKey(e){
  const tag = (e.target && e.target.tagName || '').toLowerCase()
  if (tag==='input' || tag==='textarea' || (e.target && e.target.isContentEditable)) return
  if (e.key==='n' || e.key==='N'){ e.preventDefault(); quickAddToday() }
  else if (e.key==='?'){ e.preventDefault(); notify('Shortcuts: N = new card today, ←/→ = week nav, ? = help','info',4200) }
  else if (e.key==='ArrowLeft'){ prevWeek(); e.preventDefault() }
  else if (e.key==='ArrowRight'){ nextWeek(); e.preventDefault() }
}
function quickAddToday(){
  const todayK = dateKey(new Date())
  if (!headerDays.value.some(d => d.key === todayK)) goToToday()

  const lane = swimlanes.value[0]
  if (!lane){ addLane(); return }

  const keys = headerDays.value.map(d => d.key)
  const targetKey = keys.includes(todayK) ? todayK : (keys[0] || null)
  if (!targetKey) return

  const col = lane.columns.find(c => c.dayKey === targetKey)
  if (col) addCard(lane, col)
}

function mapEntryToCard(e) {
  const parsed = parsePriorityAndCleanNotes(e.notes || '')
  const clean = String(parsed.notes || '').replace(/\r\n/g, '\n')
  const parts = clean.split('\n')
  const desc = (parts.shift() || '').trim()
  const notes = parts.join('\n').trim()

  return {
    id: String(e.id),
    jobTitle: e.job_title || '',
    projectCode: e.project_code,
    activity: e.activity,
    description: desc,
    notes: notes,
    priority: parsed.priority,
    start_utc: e.start_utc,
    end_utc: e.end_utc,
    seconds: e.seconds || 0
  }
}

function buildEmptySwimlane(key, title) {
  return {
    key,
    title,
    columns: headerDays.value.map(d => ({ dayKey: d.key, cards: [] }))
  }
}

// Map raw API entries -> UI lanes/columns. Ensures all custom lanes exist and preserves per-cell order from storage.
function assignCardsToGrid(entries) {
  const lanesMap = new Map()
  const ensureLane = (k, t) => {
    if (!lanesMap.has(k)) lanesMap.set(k, buildEmptySwimlane(k, t))
    return lanesMap.get(k)
  }

  for (const e of entries) {
    const k = groupBy.value === 'project_code' ? (e.project_code || '') : (e.activity || '')
    if (!k) continue
    const lane = ensureLane(k, k)
    const day = laneKeyFromISO(e.start_utc)
    const col = lane.columns.find(c => c.dayKey === day)
    if (col) col.cards.push(mapEntryToCard(e))
  }

  const customs = loadCustomLanes()
  // Ensure all custom lanes exist (even if no entries yet)
  for (const name of customs) {
    if (!lanesMap.has(name)) lanesMap.set(name, buildEmptySwimlane(name, name))
  }
  // Order: custom lanes first (by saved order), then the rest
  const ordered = []
  for (const name of customs) ordered.push(lanesMap.get(name))
  for (const [k, v] of lanesMap) if (!customs.includes(k)) ordered.push(v)
  // No fallback Ungrouped lane

  swimlanes.value = ordered
  applyLocalOrder()
}

// Load the current week’s entries from the server. We request [Mon..Mon+7) and then map into the grid.
// If an entry that was running disappears due to week navigation, clear the local running pointer.
async function load() {
  loading.value = true; error.value = ''
  try {
    const monday = currentWeekStart.value
    const nextMonday = addDays(monday, 7)
    const qs = new URLSearchParams({ from: monday.toISOString(), to: nextMonday.toISOString() }).toString()
    const res = await apiFetch(`${API_BASE}/api/time-entries/?${qs}`)
    if (!res.ok) throw new Error(await res.text())
    const data = await res.json()
    assignCardsToGrid(data)
    // If running id is no longer in the fetched set (e.g., week navigation), clear pointer
    try {
      if (runningId.value) {
        const found = swimlanes.value.some(l => l.columns.some(c => c.cards.some(x => String(x.id) === String(runningId.value))))
        if (!found) setRunningId(null)
      }
    } catch {}
  } catch (e) {
    error.value = String(e)
    notify(`Failed to load entries: ${error.value}`, 'error', 5000)
    assignCardsToGrid([]) // still render custom lanes
  } finally {
    loading.value = false
  }
}

// Persist order per cell (week + group + lane + day)
function orderKey(laneKey, dayKey) {
  const wk = `${currentWeekStart.value.getFullYear()}-${pad(currentWeekStart.value.getMonth()+1)}-${pad(currentWeekStart.value.getDate())}`
  return `logger.cardOrder:${wk}:${groupBy.value}:${laneKey}:${dayKey}`
}
function onReorderCell(lane, dayKey) {
  const ids = lane.columns.find(c => c.dayKey === dayKey)?.cards.map(c => c.id) || []
  localStorage.setItem(orderKey(lane.key, dayKey), JSON.stringify(ids))
}
function applyLocalOrder() {
  for (const lane of swimlanes.value) {
    for (const col of lane.columns) {
      const order = JSON.parse(localStorage.getItem(orderKey(lane.key, col.dayKey)) || '[]')
      if (!order.length) continue
      const byId = new Map(col.cards.map(c => [c.id, c]))
      const reordered = []
      for (const id of order) if (byId.has(id)) reordered.push(byId.get(id))
      for (const c of col.cards) if (!order.includes(c.id)) reordered.push(c)
      col.cards = reordered
    }
  }
}
function customLanesKey() {
  const uid = currentUserId() || 'anon'
  return `logger.customLanes:${uid}:${groupBy.value}`
}
function loadCustomLanes() {
  try { return JSON.parse(localStorage.getItem(customLanesKey()) || '[]') } catch { return [] }
}
function saveCustomLanes(names) { localStorage.setItem(customLanesKey(), JSON.stringify(names)) }
const showLaneInput = ref(false)
const laneInput = ref('')

function beginAddLane () {
  laneInput.value = ''
  showLaneInput.value = true
}

function cancelAddLane () {
  showLaneInput.value = false
  laneInput.value = ''
}

function confirmAddLane () {
  const label = laneInput.value.trim()
  if (!label) {
    // Nothing entered; just close
    showLaneInput.value = false
    return
  }

  const exists = swimlanes.value.some(l => l.key === label || l.title === label)
  if (!exists) {
    const lane = buildEmptySwimlane(label, label)
    swimlanes.value = [lane, ...swimlanes.value]
  }

  const names = loadCustomLanes()
  if (!names.includes(label)) {
    names.push(label)
    saveCustomLanes(names)
  }

  showLaneInput.value = false
  laneInput.value = ''
}
function addLane() {
  beginAddLane()
}

// Create / Update / Delete
async function saveCard(payload) {
  if (payload.id && String(payload.id).startsWith('tmp_')) payload.id = null

  if (payload.id) {
    const res = await apiFetch(`${API_BASE}/api/time-entries/${payload.id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': getCsrf() },
      body: JSON.stringify({
        project_code: payload.project_code || payload.projectCode,
        activity: payload.activity,
        job_title: payload.job_title ?? payload.jobTitle ?? null,
        start_utc: payload.start_utc,
        end_utc: payload.end_utc ? payload.end_utc : null,
        notes: `[prio:${(payload.priority || 'Normal').toLowerCase()}]` + (payload.notes ? ` ${payload.notes}` : '')
      })
    })
    if (!res.ok) {
      const msg = await extractErrorMessage(res)
      return notify(`Failed to update: ${msg}`, 'error', 6000)
    }
  } else {
    const res = await apiFetch(`${API_BASE}/api/time-entries/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': getCsrf() },
      body: JSON.stringify({
        project_code: payload.project_code || payload.projectCode,
        activity: payload.activity,
        job_title: payload.job_title ?? payload.jobTitle ?? null,
        start_utc: payload.start_utc,
        end_utc: payload.end_utc ? payload.end_utc : null,
        notes: `[prio:${(payload.priority || 'Normal').toLowerCase()}]` + (payload.notes ? ` ${payload.notes}` : '')
      })
    })
    if (!res.ok) {
      const msg = await extractErrorMessage(res)
      return notify(`Failed to create: ${msg}`, 'error', 6000)
    }
  }
  await load()
  await loadProjects()
}

async function deleteCard(lane, col, card) {
  if (!card.id || String(card.id).startsWith('tmp_')) {
    col.cards = col.cards.filter(c => c !== card)
    return
  }
  const res = await apiFetch(`${API_BASE}/api/time-entries/${card.id}`, {
    method: 'DELETE',
    headers: { 'X-CSRF-Token': getCsrf() }
  })
  if (!res.ok) {
    const msg = await extractErrorMessage(res)
    return notify(`Failed to delete: ${msg}`, 'error', 6000)
  }
  await load()
  await loadProjects()
}

function addCard(lane, col) {
  const now = new Date()
  const hm = `${pad(now.getHours())}:${pad(now.getMinutes())}`
  const startLocal = roundDateToIncrement(new Date(`${col.dayKey}T${hm}`), 'round')
  const endLocal   = new Date(startLocal.getTime() + _normInc() * 60000)

  const card = {
    id: (crypto?.randomUUID?.() || `tmp_${Date.now()}_${Math.random().toString(16).slice(2)}`),
    jobTitle: '',
    projectCode: groupBy.value === 'project_code' ? lane.title : '',
    activity: groupBy.value === 'activity' ? lane.title : '',
    description: '',
    notes: '',
    start_utc: startLocal.toISOString(),
    end_utc: endLocal.toISOString()
  }
  card.__new = true
  col.cards.unshift(card)
}

// Handle drags across rows/columns
// Drag & drop between days/lanes: recompute start/end ISO strings for the target day; update grouping fields;
// persist to server when moving existing (non-temp) cards; store new order for this cell.
function onCellChange(lane, col, evt) {
  if (evt?.added) {
    const card = evt.added.element
    const startHM = roundHMToIncrement(timeHMFromISO(card.start_utc || new Date().toISOString()), 'round')
    const endHM   = roundHMToIncrement(timeHMFromISO(card.end_utc || card.start_utc || new Date().toISOString()), 'round')
    card.start_utc = composeISOFromLaneAndTime(col.dayKey, startHM)
    card.end_utc   = composeISOFromLaneAndTime(col.dayKey, endHM)

    if (groupBy.value === 'project_code') card.project_code = lane.title
    if (groupBy.value === 'activity')     card.activity     = lane.title

    if (card.id && !String(card.id).startsWith('tmp_')) {
      saveCard(card)
    }
  }
  onReorderCell(lane, col.dayKey)
}

// Totals
// Aggregation helpers: per-day, per-lane, and per-cell hours. Used for badges and progress bar.
function colHours(dayKey) {
  let sum = 0
  for (const lane of swimlanes.value) {
    const col = lane.columns.find(c => c.dayKey === dayKey)
    if (col) sum += col.cards.reduce((s, c) => s + hoursBetweenRounded(c.start_utc, c.end_utc), 0)
  }
  return sum
}
function laneHours(lane) {
  return lane.columns.reduce((tot, c) => tot + c.cards.reduce((s, x) => s + hoursBetweenRounded(x.start_utc, x.end_utc), 0), 0)
}
function laneEntryCount (lane) {
  try {
    return lane.columns.reduce(
      (tot, c) => tot + (c.cards ? c.cards.length : 0),
      0
    )
  } catch {
    return 0
  }
}
function cellHours(lane, dayKey) {
  const col = lane.columns.find(c => c.dayKey === dayKey)
  if (!col) return 0
  return col.cards.reduce((s, c) => s + hoursBetweenRounded(c.start_utc, c.end_utc), 0)
}
const weeklyHours = computed(() => headerDays.value.reduce((tot, d) => tot + colHours(d.key), 0))
const weeklyPct = computed(() => Math.min(1, (TARGET_WEEKLY_HOURS ? (weeklyHours.value / TARGET_WEEKLY_HOURS) : 0)))

watch([currentWeekStart, groupBy], () => { load() })
</script>

<template>
  <section class="board">
    <div class="toastbox">
      <div v-for="t in toasts" :key="t.id" class="toast" :class="t.type">{{ t.msg }}</div>
    </div>
    <header class="board__header">
      <div class="nav">
        <button type="button" @click="prevWeek" title="Previous week">◀︎</button>
        <button type="button" @click="goToToday" title="This week">This Week</button>
        <button type="button" @click="nextWeek" title="Next week">▶︎</button>
        <span class="range">{{ weekLabel }}</span>
      </div>
      <div class="toolbar">
        <label class="group">
          Group by
          <select v-model="groupBy">
            <option v-for="g in GROUPS" :key="g.value" :value="g.value">{{ g.label }}</option>
          </select>
        </label>
        <label class="group">
          Layout
          <select v-model="layoutMode">
            <option value="grid">Board</option>
            <option value="simple">Simple</option>
          </select>
        </label>
        <label class="group">
          Increment
          <select v-model.number="incrementMinutes">
            <option :value="5">5 min</option>
            <option :value="10">10 min</option>
            <option :value="15">15 min</option>
            <option :value="20">20 min</option>
            <option :value="30">30 min</option>
          </select>
        </label>
        <div class="goal">
          <div class="bar"><i :style="{ width: (weeklyPct*100)+'%' }"></i></div>
          <span>{{ fmtH(weeklyHours, 2) }} / {{ TARGET_WEEKLY_HOURS }} h</span>
        </div>
                <div v-if="runningLaneTitle" class="running-pill">
          Running: <span class="running-pill__name">{{ runningLaneTitle }}</span>
        </div>
                <div class="toolbar__add">
          <button type="button" @click="addLane">
            {{ groupBy === 'project_code' ? 'Add Project' : 'Add Activity' }}
          </button>
          <div v-if="showLaneInput" class="toolbar__add-inline">
            <input
              v-model="laneInput"
              type="text"
              :placeholder="groupBy === 'project_code' ? 'Project name' : 'Activity name'"
              @keyup.enter="confirmAddLane"
            />
            <button type="button" class="mini" @click="confirmAddLane">OK</button>
            <button type="button" class="mini" @click="cancelAddLane">Cancel</button>
          </div>
        </div>
        <button
          type="button"
          @click="toggleTheme"
          :title="theme==='dark' ? 'Switch to Light' : 'Switch to Dark'"
        >
          {{ theme==='dark' ? '☀︎' : '🌙' }}
        </button>
      </div>
    </header>
    

      <p v-if="error" class="error">{{ error }}</p>
      <p v-if="loading">Loading…</p>
      <TodayLog
        :layout-mode="layoutMode"
        :current-week-start="currentWeekStart"
        :header-days="headerDays"
        :swimlanes="swimlanes"
        :running-id="runningId"
        :now-tick="nowTick"
        :fmt-h="fmtH"
        :col-hours="colHours"
        :get-lane-meta="getLaneMeta"
        :lane-visible-on-day-by-projects="laneVisibleOnDayByProjects"
        :is-lane-running="isLaneRunning"
        :priorities="PRIORITIES"
        :lane-meta-draft="laneMetaDraft"
        :is-editing-lane-meta="isEditingLaneMeta"
        :edit-lane-meta="editLaneMeta"
        :save-lane-meta="saveLaneMeta"
        :cancel-lane-meta-edit="cancelLaneMetaEdit"
        :start-lane-timer="startLaneTimer"
        :start-timer="startTimer"
        :stop-timer="stopTimer"
        :add-card="addCard"
        :save-card="saveCard"
        :delete-card="deleteCard"
        :on-cell-change="onCellChange"
        :on-reorder-cell="onReorderCell"
      />
      <!-- Weekly Board/Grid extracted into WeekLog.vue -->
      <WeekLog
        :layout-mode="layoutMode"
        :header-days="headerDays"
        :swimlanes="swimlanes"
        :running-id="runningId"
        :now-tick="nowTick"
        :increment-minutes="incrementMinutes"
        :fmt-h="fmtH"
        :col-hours="colHours"
        :lane-hours="laneHours"
        :lane-entry-count="laneEntryCount"
        :cell-hours="cellHours"
        :get-lane-meta="getLaneMeta"
        :lane-desc="laneDesc"
        :is-lane-running="isLaneRunning"
        :priorities="PRIORITIES"
        :lane-meta-draft="laneMetaDraft"
        :is-editing-lane-meta="isEditingLaneMeta"
        :edit-lane-meta="editLaneMeta"
        :save-lane-meta="saveLaneMeta"
        :cancel-lane-meta-edit="cancelLaneMetaEdit"
        :start-lane-timer="startLaneTimer"
        :start-timer="startTimer"
        :stop-timer="stopTimer"
        :add-card="addCard"
        :save-card="saveCard"
        :delete-card="deleteCard"
        :on-cell-change="onCellChange"
        :on-reorder-cell="onReorderCell"
      />
    <!-- Simple layout: per-day stacks per project -->
    <!-- Simple layout: projects/activities as columns; entries stacked vertically per selected day. -->
    <section v-if="layoutMode==='simple'" class="simple">
      <div class="simple__days">
        <button
          v-for="d in headerDays"
          :key="d.key"
          :class="['simple__daybtn', { active: d.key === selectedDayKey }]"
          @click="selectedDayKey = d.key"
        >
          <span class="lbl">{{ d.label }}</span>
          <small class="sum">{{ fmtH(colHours(d.key), 2) }} h</small>
        </button>
      </div>
      <div class="simple__lanes">
        <div class="simple__lane" v-for="lane in swimlanes" :key="lane.key">
          <header class="simple__lanehead">
            <h3 class="title">{{ lane.title }}</h3>
            <div class="right">
              <span class="badge hours">{{ fmtH(cellHours(lane, selectedDayKey), 2) }} h</span>
              <!-- Single toggle: Start new entry (also stops previous) / Stop running entry -->
              <button class="mini icon"
                      @click="isLaneRunning(lane) ? stopTimer() : startLaneTimer(lane)"
                      :title="isLaneRunning(lane) ? 'Stop' : 'Start a new entry'">
                {{ isLaneRunning(lane) ? '■' : '▶︎' }}
              </button>
            </div>
          </header>

          <div class="simple__entries">
            <div
              v-if="colFor(lane, selectedDayKey).cards.length"
              class="simple__droplist"
            >
              <TimeCard
                v-for="(element, index) in colFor(lane, selectedDayKey).cards"
                :key="element.id"
                :card="element"
                :compact="true"
                :tab-side="(index % 2 === 0) ? 'left' : 'right'"
                :collapsed="false"
                :increment-minutes="incrementMinutes"
                :open-on-mount="element.__new === true"
                :running-id="runningId"
                :now-tick="nowTick"
                @start="startTimer"
                @stop="stopTimer"
                @save="saveCard"
                @delete="c => deleteCard(lane, colFor(lane, selectedDayKey), c)"
              />
            </div>

          </div>
        </div>
      </div>
    </section>
  </section>
</template>

<style scoped>
/*
  TimeBoard styles
  - Board chrome: header/nav/toolbars and progress bar
  - Grid layout: weekly matrix cells, row headers, drag/drop styling
  - Focus (today) panel
  - Simple layout: per-day columns
  - Toast notifications
*/

/* Shell / board chrome */
.board {
  max-width: var(--container);
  margin: 0 auto;
  padding: 12px;
}

.board__header {
  display: grid;
  grid-template-columns: 1fr auto;
  align-items: center;
  gap: 12px;
  position: sticky;
  top: 0;
  z-index: 10;
  padding: 10px 0 12px;
  background: var(--bg);
  border-bottom: 1px solid var(--border);
}


/* Top nav + toolbar */
.nav {
  display: flex;
  align-items: center;
  gap: 6px;
}

.nav button {
  padding: 0.36rem 0.55rem;
  color: var(--primary);
  border: 1px solid var(--border);
  background: var(--btn-blue-bg);
  border-radius: 10px;
  cursor: pointer;
}

.nav button:hover {
  background: var(--btn-blue-bg-hover);
}

.range {
  margin-left: 0.4rem;
  font-weight: 700;
  color: var(--text);
}

.toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
}

.toolbar button {
  padding: 0.36rem 0.55rem;
  color: var(--primary);
  border: 1px solid var(--border);
  background: var(--btn-blue-bg);
  border-radius: 10px;
  cursor: pointer;
}

.toolbar button:hover {
  background: var(--btn-blue-bg-hover);
}

.group {
  display: flex;
  align-items: center;
  gap: 6px;
  color: var(--muted);
  font-weight: 600;
}

select {
  background: var(--panel);
  color: var(--text);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 0.3rem 0.45rem;
}

/* Add lane inline input */
.toolbar__add {
  display: flex;
  align-items: center;
  gap: 6px;
}

.toolbar__add-inline {
  display: flex;
  align-items: center;
  gap: 4px;
}

.toolbar__add-inline input {
  padding: 0.3rem 0.45rem;
  border-radius: 8px;
  border: 1px solid var(--border);
  background: var(--panel-2);
  color: var(--text);
  min-width: 180px;
}


/* Weekly goal bar */
.goal {
  display: flex;
  align-items: center;
  gap: 8px;
}

.goal .bar {
  width: 180px;
  height: 8px;
  border-radius: 999px;
  background: #e2e8f0;
  overflow: hidden;
  border: 1px solid var(--border);
}

.goal .bar i {
  display: block;
  height: 100%;
  background: linear-gradient(90deg, var(--primary), var(--accent));
}

.goal span {
  color: var(--muted);
  font-weight: 700;
}

/* Running lane pill (toolbar) */
.running-pill {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 0.2rem 0.6rem;
  border-radius: 999px;
  background: color-mix(in srgb, var(--primary) 10%, transparent);
  border: 1px solid color-mix(in srgb, var(--border) 60%, var(--primary) 40%);
  font-size: 0.8rem;
  color: var(--text);
}

.running-pill__name {
  font-weight: 600;
}

/* Toasts */
.hours {
  /* Day total: plain text, no pill container */
  background: transparent;
  border: none;
  padding: 0;
  border-radius: 0;
  font-weight: 600;
  color: var(--muted);
}
.toastbox {
  position: fixed;
  top: 12px;
  right: 16px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  z-index: 1200;
  pointer-events: none;
}

.toast {
  min-width: 260px;
  max-width: 360px;
  padding: 0.55rem 0.75rem;
  border-radius: 10px;
  background: var(--panel-2);
  border: 1px solid var(--border);
  box-shadow: var(--shadow-md);
  font-size: 0.85rem;
  color: var(--text);
  pointer-events: auto;
  animation: toast-drop-in 0.18s ease-out;
}

.toast.info {
  border-color: color-mix(in srgb, var(--border) 70%, var(--primary) 30%);
}

.toast.success {
  border-color: #16a34a40;
  background: #ecfdf3;
  color: #166534;
}

.toast.error {
  border-color: #fecaca;
  background: #fef2f2;
  color: #991b1b;
}

@keyframes toast-drop-in {
  from {
    opacity: 0;
    transform: translateY(-8px) translateX(4px);
  }
  to {
    opacity: 1;
    transform: translateY(0) translateX(0);
  }
}

/* Error text */
.error {
  color: #b91c1c;
}

/* --- Simple layout (per-day columns) --- */
.simple {
  display: grid;
  gap: 16px;
  margin-top: 12px;
}

/* Day chips */
.simple__days {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  position: sticky;
  top: 64px;
  z-index: 2;
}

.simple__daybtn {
  display: inline-flex;
  align-items: baseline;
  gap: 6px;
  border: 1px solid var(--border);
  background: var(--panel);
  color: var(--text);
  border-radius: 999px;
  padding: 0.35rem 0.7rem;
  cursor: pointer;
  box-shadow: var(--shadow-sm);
}

.simple__daybtn.active {
  background: var(--btn-blue-bg);
}

/* Projects/activities as columns */
.simple__lanes {
  display: grid;
  grid-auto-flow: column;
  grid-auto-columns: minmax(260px, 1fr);
  gap: 16px;
  align-items: start;
  overflow-x: auto;
  padding-bottom: 4px;
}

.simple__lane {
  display: grid;
  grid-template-rows: auto 1fr;
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 14px;
  box-shadow: var(--shadow-sm);
  min-height: 280px;
}

.simple__lanehead {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.simple__lanehead .title {
  margin: 0;
  font-size: 1.05rem;
}

.simple__lanehead .right {
  display: inline-flex;
  gap: 6px;
  align-items: center;
}

/* Entries container in each lane */
.simple__entries {
  display: block;
}

/* Make entries stack and cascade like folders */
.simple__droplist {
  display: grid;
  gap: 12px;
  grid-template-columns: 1fr;   /* single column of entry cards */
  align-items: start;
  overflow-y: auto;
  max-height: 60vh;              /* keep columns tidy; adjust as needed */
}

/* Folder-style cascading stack for compact cards in Simple layout */
.simple__droplist :deep(.tcard.compact) {
  position: relative;
  margin-top: -12px;        /* overlap cards so tabs cascade */
  z-index: 1;
}

.simple__droplist :deep(.tcard.compact:first-child) {
  margin-top: 0;            /* top card starts the stack */
}

/* Slight lift on hover so the active card is visually on top */
.simple__droplist :deep(.tcard.compact:hover) {
  z-index: 5;
}
</style>