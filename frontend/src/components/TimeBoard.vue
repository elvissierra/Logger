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
import draggable from 'vuedraggable'
import TimeCard from './TimeCard.vue'
import { API_BASE, apiFetch, getCsrf } from '../lib/api'
import {
  pad, startOfWeek, addDays, dateKey, labelFor,
  timeHMFromISO, composeISOFromLaneAndTime, laneKeyFromISO,
  hoursBetweenRounded, roundHMToQuarter, roundDateToQuarter,
  fmtH, isSameDay
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
const TARGET_WEEKLY_HOURS = 40
function setUserId(id){ localStorage.setItem('logger.userId', id) }



// Per-user running timer pointer: saved under key logger.runningEntry:<userId> so multiple users on the same browser
// don’t clash. We clear the key on stop or when navigating to a week where the entry is not present.
// --- Running timer pointer (client-side) ---
function setRunningId (id) {
  runningId.value = id
  const rk = runningKey()
  if (!rk) return
  if (id) localStorage.setItem(rk, id)
  else localStorage.removeItem(rk)
}
async function stopRunningIfAny () {
  if (!runningId.value) return { stopped: false, id: null, error: null }

  const id = runningId.value
  try {
    const res = await apiFetch(`${API_BASE}/api/time-entries/${id}`, {
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRF-Token': getCsrf()
      },
      body: JSON.stringify({ end_utc: new Date().toISOString() })
    })

    if (!res.ok) {
      const msg = await extractErrorMessage(res)
      notify(`Could not stop existing timer: ${msg}`, 'error', 6000)
      return { stopped: false, id, error: msg }
    }

    setRunningId(null)
    await load()
    return { stopped: true, id, error: null }
  } catch (e) {
    const msg = e?.message || String(e)
    notify(`Could not stop existing timer: ${msg}`, 'error', 6000)
    return { stopped: false, id, error: msg }
  }
}
// Start a timer: stop any existing one, create a new *running* entry (end_utc=null).
async function startTimer (seedCard) {
  const { error } = await stopRunningIfAny()
  if (error) {
    // Backend still thinks a timer is running; don’t try to start another.
    return
  }

  const now = new Date()
  const payload = {
    
    project_code: seedCard.project_code || seedCard.projectCode || '',
    activity: seedCard.activity || '',
    job_title: seedCard.job_title || seedCard.jobTitle || null,
    start_utc: now.toISOString(),
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
      if (col.cards && col.cards.some(x => x.id === runningId.value)) return true
    }
    return false
  } catch { return false }
}

const runningLaneTitle = computed(() => {
  if (!runningId.value) return ''
  try {
    for (const lane of swimlanes.value) {
      for (const col of lane.columns) {
        if (col.cards && col.cards.some(c => c.id === runningId.value)) {
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
    notes: meta.description || ''
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
// --- Lane description clamp/expand state ---
const expandedLanes = ref({})
function laneDesc(key){ return (getLaneMeta(key).description || '') }
function isDescLong(key){ return laneDesc(key).length > 120 }
function isExpanded(key){ return !!expandedLanes.value[key] }
function toggleMoreDesc(key){ expandedLanes.value[key] = !expandedLanes.value[key] }


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
  if (!todayKey.value) goToToday()
  const lane = swimlanes.value[0]
  if (!lane){ addLane(); return }
  const col = lane.columns.find(c=>c.dayKey===(todayKey.value||headerDays.value[0].key))
  if (col) addCard(lane, col)
}

function mapEntryToCard(e) {
  const parsed = parsePriorityAndCleanNotes(e.notes || '')
  return {
    id: e.id,
    jobTitle: e.job_title || '',
    projectCode: e.project_code,
    activity: e.activity,
    description: '',
    notes: parsed.notes,
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
        const found = swimlanes.value.some(l => l.columns.some(c => c.cards.some(x => x.id === runningId.value)))
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
  const startLocal = roundDateToQuarter(new Date(`${col.dayKey}T${hm}`))
  const endLocal   = new Date(startLocal.getTime() + 15 * 60000)

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
    const startHM = roundHMToQuarter(timeHMFromISO(card.start_utc || new Date().toISOString()))
    const endHM   = roundHMToQuarter(timeHMFromISO(card.end_utc || startHM))
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
const todayLabel = computed(() => todayHeader.value ? todayHeader.value.label : '')

// ---- Focus: enlarge the current day's column at the top ----
const todayHeader = computed(() => headerDays.value.find(d => isSameDay(d.date, new Date())))
const todayKey = computed(() => todayHeader.value?.key || null)
const showFocus = computed(() => !!todayKey.value && isSameDay(currentWeekStart.value, startOfWeek(new Date())))

// Per-day plan note (local persistence for now; can be moved to backend later)
const dailyPlan = ref('')
function planKey(dayKey) {
  const uid = currentUserId()
  return uid ? `logger.dailyPlan:${uid}:${dayKey}` : null
}
watch(todayKey, (k) => {
  const key = k ? planKey(k) : null
  dailyPlan.value = key ? (localStorage.getItem(key) || '') : ''
}, { immediate: true })
watch(dailyPlan, (v) => {
  const k = todayKey.value
  const key = k ? planKey(k) : null
  if (key) localStorage.setItem(key, v)
})

// Aggregate today's cards across all swimlanes
// Today focus: flattens each lane’s Today column for a larger editor area at the top of the page.
const todayLanes = computed(() => {
  if (!todayKey.value) return []
  return swimlanes.value
    .filter(lane => laneVisibleOnDayByProjects(lane.key, todayKey.value))
    .map(lane => ({
      lane,
      col: lane.columns.find(c => c.dayKey === todayKey.value) || { dayKey: todayKey.value, cards: [] },
    }))
})

// Effects

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
    <!-- Focus area (today): quick editing surface and lane-level actions like start/stop. -->
    <section v-if="layoutMode==='grid' && showFocus" class="focus focus--inboard">
      <header class="focus__header">
        <strong>Today — {{ todayLabel }}</strong>
        <span class="focus__hours">{{ fmtH(colHours(todayKey), 2) }} h</span>
      </header>
      <div class="focus__layout">
        <aside class="focus__plan">
          <label class="focus__label">Today's plan</label>
          <textarea
            v-model="dailyPlan"
            rows="6"
            class="focus__textarea"
            placeholder='e.g., "this is what I plan to work on today"'
          ></textarea>
        </aside>

        <div class="focus__col">
          <div
            v-for="pair in todayLanes"
            :key="pair.lane.key"
            class="focus__lane"
          >
            <div class="focus__lanehead">
              <div class="lane-title">
                <strong>{{ pair.lane.title }}</strong>
                <span
                  v-if="getLaneMeta(pair.lane.key).priority"
                  class="badge"
                  :class="'p-' + (getLaneMeta(pair.lane.key).priority || 'Normal').toLowerCase()"
                >
                  {{ getLaneMeta(pair.lane.key).priority }}
                </span>
                <span
                  v-if="isLaneRunning(pair.lane)"
                  class="badge badge--running"
                >
                  Running
                </span>
              </div>
              <div class="lane-actions">
                <button
                  class="mini icon"
                  @click="isLaneRunning(pair.lane) ? stopTimer() : startLaneTimer(pair.lane)"
                  :title="isLaneRunning(pair.lane) ? 'Stop timer' : 'Start timer'"
                >
                  {{ isLaneRunning(pair.lane) ? '■' : '▶︎' }}
                </button>
                <button
                  class="mini icon"
                  @click="editLaneMeta(pair.lane)"
                  title="Edit project settings"
                >
                  ⋯
                </button>
                <button
                  v-if="laneVisibleOnDayByProjects(pair.lane.key, pair.col.dayKey)"
                  class="mini icon"
                  @click="addCard(pair.lane, pair.col)"
                  title="Add card"
                >
                  ＋
                </button>
              </div>
            </div>

            <div
              v-if="isEditingLaneMeta(pair.lane.key)"
              class="lane-meta-editor lane-meta-editor--focus"
            >
              <label class="lane-meta-editor__field">
                <span>Priority</span>
                <select v-model="laneMetaDraft.priority">
                  <option v-for="p in PRIORITIES" :key="p" :value="p">{{ p }}</option>
                </select>
              </label>
              <label class="lane-meta-editor__field">
                <span>Description</span>
                <textarea
                  v-model="laneMetaDraft.description"
                  rows="2"
                  placeholder="What does this lane represent?"
                ></textarea>
              </label>
              <div class="lane-meta-editor__actions">
                <button type="button" class="mini" @click="saveLaneMeta(pair.lane)">Save</button>
                <button type="button" class="mini" @click="cancelLaneMetaEdit">Cancel</button>
              </div>
            </div>
            <div
              v-else-if="getLaneMeta(pair.lane.key).description"
              class="focus__lanedesc"
            >
              {{ getLaneMeta(pair.lane.key).description }}
            </div>
            <draggable
              v-model="pair.col.cards"
              item-key="id"
              :animation="160"
              handle=".handle"
              class="focus__droplist"
              :group="{ name: 'cards', pull: true, put: true }"
              ghost-class="drag-ghost"
              chosen-class="drag-chosen"
              drag-class="drag-dragging"
              @change="onCellChange(pair.lane, pair.col, $event)"
              @end="onReorderCell(pair.lane, pair.col.dayKey)"
            >
              <template #item="{ element }">
                <TimeCard :card="element" :open-on-mount="element.__new === true"
                          :running-id="runningId" :now-tick="nowTick"
                          @start="startTimer" @stop="stopTimer"
                          @save="saveCard" @delete="c => deleteCard(pair.lane, pair.col, c)" />
              </template>
            </draggable>
          </div>
        </div>
      </div>
    </section>

      <p v-if="error" class="error">{{ error }}</p>
      <p v-if="loading">Loading…</p>
        
      <!-- Scroller keeps header row and columns aligned on all widths -->
      <!-- Weekly Board/Grid: 7-day matrix with swimlanes on rows; entries rendered only when present in a cell. -->
      <div class="board__scroller" v-if="layoutMode==='grid'">
        <h2 class="board__sectiontitle">Weekly log</h2>
        <div class="grid">
        <!-- Header row -->
        <div class="cell cell--head"></div>
        <div v-for="d in headerDays" :key="d.key" class="cell cell--head">
          <div class="dayhead">
            <strong>{{ d.label }}</strong>
            <small>{{ fmtH(colHours(d.key), 2) }} h</small>
          </div>
        </div>

        <!-- Swimlane rows -->
        <template v-for="lane in swimlanes" :key="lane.key">
        <div class="cell cell--rowhead">
          <article
            class="projcard"
            :class="'prio-' + String((getLaneMeta(lane.key).priority || 'Normal')).toLowerCase()"
          >
            <!-- Row 1: color dot + project name -->
            <header class="projcard__head">
              <h4
                class="title"
                :title="lane.title + (laneDesc(lane.key) ? ' — ' + laneDesc(lane.key) : '')"
              >
                {{ lane.title }}
              </h4>
              <span
                v-if="isLaneRunning(lane)"
                class="projcard__running-icon"
                title="Timer running"
                aria-label="Timer running"
              >
                🌀
              </span>
            </header>
          
            <!-- Row 2: hours + summary + running icon -->
            <div class="projcard__hoursrow">
              <span class="projcard__hours-pill">
                {{ fmtH(laneHours(lane), 2) }} h
              </span>
            
              <span
                v-if="laneEntryCount(lane)"
                class="projcard__entries"
              >
                {{ laneEntryCount(lane) }} entr<span v-if="laneEntryCount(lane) !== 1">ies</span>
              </span>
            
            </div>
          
            <!-- Row 3: buttons -->
            <footer class="projcard__foot">
              <div class="spacer"></div>
              <div class="actions__icons">
                <button
                  class="mini icon"
                  @click="isLaneRunning(lane) ? stopTimer() : startLaneTimer(lane)"
                  :title="isLaneRunning(lane) ? 'Stop timer' : 'Start timer'"
                >
                  {{ isLaneRunning(lane) ? '■' : '▶︎' }}
                </button>
                <button
                  class="mini icon"
                  @click="editLaneMeta(lane)"
                  title="Edit project settings"
                >
                  ⋯
                </button>
              </div>
            </footer>
            <div
              v-if="isEditingLaneMeta(lane.key)"
              class="lane-meta-editor lane-meta-editor--row"
            >
              <label class="lane-meta-editor__field">
                <span>Priority</span>
                <select v-model="laneMetaDraft.priority">
                  <option v-for="p in PRIORITIES" :key="p" :value="p">{{ p }}</option>
                </select>
              </label>
              <label class="lane-meta-editor__field">
                <span>Description</span>
                <textarea
                  v-model="laneMetaDraft.description"
                  rows="2"
                  placeholder="Short description for this lane"
                ></textarea>
              </label>
              <div class="lane-meta-editor__actions">
                <button type="button" class="mini" @click="saveLaneMeta(lane)">Save</button>
                <button type="button" class="mini" @click="cancelLaneMetaEdit">Cancel</button>
              </div>
            </div>
          </article>
        </div>

          <!-- Row header cell -->
          <!-- Day cells -->
          <template v-for="col in lane.columns" :key="lane.key + ':' + col.dayKey">
            <div class="cell">
              <div class="cell__sum" v-if="cellHours(lane, col.dayKey)">{{ fmtH(cellHours(lane, col.dayKey), 2) }} h</div>
              <div class="cell__actions">
                <button class="mini icon" @click="addCard(lane, col)" title="Add card to this cell">＋</button>
              </div>
              <!-- Only render the list when there are actual entries -->
              <draggable v-if="col.cards.length" v-model="col.cards"
                item-key="id"
                :animation="160"
                handle=".handle"
                class="droplist"
                :group="{ name: 'cards', pull: true, put: true }"
                ghost-class="drag-ghost"
                chosen-class="drag-chosen"
                drag-class="drag-dragging"
                @change="onCellChange(lane, col, $event)"
                @end="onReorderCell(lane, col.dayKey)"
              >
                <template #item="{ element }">
                  <TimeCard :card="element" :open-on-mount="element.__new === true"
                            :running-id="runningId" :now-tick="nowTick" :compact="true"
                            @start="startTimer" @stop="stopTimer"
                            @save="saveCard" @delete="c => deleteCard(lane, col, c)" />
                </template>
              </draggable>
            </div>
          </template>
        </template>
      </div>
    </div>
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
            <draggable
              v-if="colFor(lane, selectedDayKey).cards.length"
              v-model="colFor(lane, selectedDayKey).cards"
              item-key="id"
              :animation="160"
              handle=".handle"
              class="simple__droplist"
              :group="{ name: 'cards', pull: true, put: true }"
              ghost-class="drag-ghost"
              chosen-class="drag-chosen"
              drag-class="drag-dragging"
              @change="onCellChange(lane, colFor(lane, selectedDayKey), $event)"
              @end="onReorderCell(lane, selectedDayKey)"
            >
              <template #item="{ element }">
                <TimeCard
                  :card="element"
                  :compact="true"
                  :open-on-mount="element.__new === true"
                  :running-id="runningId"
                  :now-tick="nowTick"
                  @start="startTimer"
                  @stop="stopTimer"
                  @save="saveCard"
                  @delete="c => deleteCard(lane, colFor(lane, selectedDayKey), c)"
                />
              </template>
            </draggable>

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

.board__sectiontitle {
  margin: 4px 6px 8px;
  font-size: 0.9rem;
  font-weight: 650;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: var(--muted);
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

/* Small icon buttons */
.mini {
  padding: 0.2rem 0.45rem;
  border: 1px solid var(--border);
  background: var(--btn-blue-bg);
  color: var(--primary);
  border-radius: 8px;
  cursor: pointer;
}

.mini:hover {
  background: var(--btn-blue-bg-hover);
}

.mini.icon {
  padding: 0.2rem;
  width: 28px;
  height: 28px;
  display: inline-grid;
  place-items: center;
  border-radius: 10px;
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

/* Weekly board scroller */
.board__scroller {
  margin-top: 6px;
  padding: 10px 10px 14px;
  background: var(--panel);
  border-radius: var(--radius);
  border: 1px solid var(--border);
  box-shadow: var(--shadow-sm);
  overflow: auto;
}

/* Spreadsheet-style weekly grid */
.grid {
  --rowhead-w: 170px;
  display: grid;
  grid-template-columns: var(--rowhead-w) repeat(7, minmax(140px, 1fr));
  gap: 8px;
  align-items: start;
  padding: 6px 0;
}

.cell {
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  min-height: 120px;
  position: relative;
  padding: 26px 6px 8px;
}

/* Container for stacked compact cards – behaves like a file-folder stack */
.cell .droplist {
  margin-top: 10px;
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 0; /* overlap provides the separation */
}

.cell .droplist :deep(.tcard.compact) {
  position: relative;
  z-index: 1;
  box-shadow: var(--shadow-sm);
  background: var(--panel);
  border-radius: 12px;
  padding: 0.75rem 0.8rem 0.7rem 0.8rem;
  min-height: 56px;

  /* Folder-stack overlap: each card tucks slightly under the one above */
  margin-top: -18px;
  transition:
    margin-top 0.15s ease,
    transform 0.12s ease,
    box-shadow 0.12s ease;
}

/* First card in the stack starts flush with the lane */
.cell .droplist :deep(.tcard.compact:first-child) {
  margin-top: 0;
}

.cell:hover {
  box-shadow: 0 0 0 1px color-mix(in srgb, var(--primary) 25%, transparent);
  border-color: color-mix(in srgb, var(--border) 60%, var(--primary) 40%);
}

.cell--head {
  background: transparent;
  border: none;
  min-height: auto;
}

/* Collapse top-left header spacer */
.grid > .cell.cell--head:first-child {
  padding: 0;
  min-height: 0;
  background: transparent;
  border: none;
  box-shadow: none;
}

/* Sticky project row headers */
.cell--rowhead {
  position: sticky;
  left: 0;
  z-index: 5;
  background: var(--panel);
  border-right: 1px solid var(--border);
  padding: 8px 6px 8px;
  overflow: visible; /* let meta editor expand */
}

.dayhead {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 6px;
  border-bottom: 1px solid var(--border);
  color: var(--muted);
  font-weight: 600;
  font-size: 0.88rem;
  white-space: nowrap;
  gap: 6px;
}

.dayhead strong {
  letter-spacing: 0.01em;
  font-weight: 600;
}

.dayhead small {
  font-weight: 600;
  opacity: 0.9;
  font-size: 0.8rem;
  flex-shrink: 0;
}

/* Per-cell summary + add button */
.cell__sum {
  position: absolute;
  top: 4px;
  left: 6px;
  font-size: 0.78rem;
  font-weight: 600;
  color: var(--muted);
  padding: 0;
  background: transparent;
  border: none;
}

.cell__actions {
  position: absolute;
  top: 6px;
  right: 6px;
}

/* Row-header project card */
.projcard {
  position: relative;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  gap: 6px;
  padding: 10px 10px 9px;
  border-radius: var(--radius);
  background: color-mix(in srgb, var(--panel-2) 92%, transparent);
  border: 1px solid color-mix(in srgb, var(--border) 85%, transparent);
  box-shadow: var(--shadow-sm);
  overflow: visible;
}

/* Folder-style strip at top of project card (color from priority) */
.projcard::before {
  content: '';
  position: absolute;
  top: 4px;
  left: 10px;
  width: 64px;
  height: 10px;
  border-radius: 10px 10px 0 0;
  background: color-mix(in srgb, var(--primary, #5b8cff) 20%, transparent);
  opacity: 0.9;
}

.projcard.prio-low::before {
  background: #93c5fd;
}
.projcard.prio-normal::before {
  background: #a5b4fc;
}
.projcard.prio-high::before {
  background: #fdba74;
}
.projcard.prio-critical::before {
  background: #fca5a5;
}

.projcard__head {
  display: flex;
  align-items: center;
  gap: 8px;
}

.projcard__head .title {
  margin: 0;
  font-size: 0.9rem;
  font-weight: 650;
  color: var(--text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.projcard__running-icon {
  font-size: 0.9rem;
  flex-shrink: 0;
}

/* Project card hours row */
.projcard__hoursrow {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-top: 2px;
  font-size: 0.78rem;
  color: var(--muted);
}

/* Make daily total hours plain text (no pill) */
.projcard__hours-pill {
  padding: 0;
  background: transparent;
  border: none;
  border-radius: 0;
  font-weight: 600;
  color: var(--muted);
}

/* Entry count text */
.projcard__entries {
  font-size: 0.75rem;
  color: var(--muted);
  white-space: nowrap;
  flex: 1;
  text-align: right;
  margin-right: 4px;
}

.projcard__foot {
  display: flex;
  align-items: center;
  margin-top: 4px;
}

.projcard__foot .spacer {
  flex: 1;
}

.projcard__foot .actions__icons {
  display: flex;
  gap: 6px;
}

.projcard__foot .mini.icon {
  background: var(--btn-blue-bg);
  border-color: var(--border);
}

.projcard__foot .mini.icon:hover {
  background: var(--btn-blue-bg-hover);
}

/* Priority dot (matches TimeCard) */
.prio-dot {
  width: 10px;
  height: 10px;
  border-radius: 999px;
  display: inline-block;
  border: 1px solid var(--border);
}

.prio-dot.p-low {
  background: #93c5fd;
  border-color: #93c5fd;
}
.prio-dot.p-normal {
  background: #a5b4fc;
  border-color: #a5b4fc;
}
.prio-dot.p-high {
  background: #fdba74;
  border-color: #fdba74;
}
.prio-dot.p-critical {
  background: #fca5a5;
  border-color: #fca5a5;
}

/* Lane meta inline editor */
.lane-meta-editor {
  margin-top: 6px;
  padding: 6px 8px;
  border-radius: 10px;
  background: color-mix(in srgb, var(--panel-2) 85%, transparent);
  border: 1px solid color-mix(in srgb, var(--border) 85%, transparent);
  display: grid;
  gap: 4px;
  border-top: 1px dashed var(--border);
}

.lane-meta-editor--focus {
  margin: 4px 0 0;
}

.lane-meta-editor--row {
  margin-top: 6px;
}

.lane-meta-editor__field {
  display: grid;
  gap: 2px;
  font-size: 0.78rem;
  color: var(--muted);
}

.lane-meta-editor__field select,
.lane-meta-editor__field textarea {
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 0.3rem 0.45rem;
  color: var(--text);
  font-size: 0.8rem;
}

.lane-meta-editor__actions {
  display: flex;
  justify-content: flex-end;
  gap: 4px;
  margin-top: 2px;
}

.lane-meta-editor textarea {
  max-height: 160px;
  resize: vertical;
}

/* Badges for priority (Today focus view) */
.badge {
  font-size: 0.72rem;
  padding: 0.1rem 0.45rem;
  border-radius: 999px;
  border: 1px solid var(--border);
}

.badge.p-low {
  background: #eef6ff;
  color: #1e3a8a;
}
.badge.p-normal {
  background: #eef2ff;
  color: #3730a3;
}
.badge.p-high {
  background: #fff7ed;
  color: #9a3412;
  border-color: #fed7aa;
}
.badge.p-critical {
  background: #fef2f2;
  color: #991b1b;
  border-color: #fecaca;
}

.badge.hours {
  /* Day total: plain text, no pill container */
  background: transparent;
  border: none;
  padding: 0;
  border-radius: 0;
  font-weight: 600;
  color: var(--muted);
}

/* Focus (today) panel */
.focus {
  width: 100%;
  margin: 12px 0 16px;
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  box-shadow: var(--shadow-sm);
}

.focus--inboard {
  max-width: 100%;
}

.focus__header {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  padding: 12px 14px;
  border-bottom: 1px solid var(--border);
}

.focus__hours {
  color: var(--muted);
  font-weight: 700;
}

.focus__layout {
  position: relative;
  display: grid;
  align-items: start;
  grid-template-columns: 340px 1fr;
  gap: 16px;
  padding: 12px;
}

@media (max-width: 1100px) {
  .focus__layout {
    grid-template-columns: 1fr;
  }
}

.focus__plan {
  display: grid;
  gap: 8px;
  position: sticky;
  top: 0;
  align-self: start;
  z-index: 0;
}

.focus__label {
  font-weight: 700;
  color: var(--muted);
  display: block;
  margin-bottom: 0.5rem;
}

.focus__textarea {
  width: 100%;
  min-height: 160px;
  resize: vertical;
  padding: 0.6rem 0.7rem;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--panel-2);
  color: var(--text);
}

.focus__col {
  display: grid;
  gap: 12px;
  position: relative;
  z-index: 1;
}

.focus__lane {
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 10px;
}

.focus__lanehead {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 10px;
  border-bottom: 1px solid var(--border);
  font-weight: 700;
}

.focus__lanedesc {
  color: var(--muted);
  font-size: 0.85rem;
  padding: 6px 10px 0;
}

.focus__droplist {
  display: grid;
  gap: 10px;
  padding: 10px;
  max-height: none;
  position: relative;
  z-index: 1;
}

/* Draggable defaults for TimeCard in focus + grid */
.droplist :deep(.tcard),
.focus :deep(.tcard) {
  background: var(--panel);
  color: var(--text);
  border-color: var(--border);
  box-shadow: var(--shadow-sm);
}

/* Drag feedback */
:global(.drag-ghost) {
  opacity: 0.6;
  transform: rotate(2deg);
}
:global(.drag-chosen) {
  box-shadow: var(--shadow-md) !important;
}
:global(.drag-dragging) {
  cursor: grabbing;
}

/* Toasts */
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