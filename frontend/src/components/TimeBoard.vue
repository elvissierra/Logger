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
 * - Auth: We call /api/auth/me to get the user and store the id in localStorage for per-user client keys.
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

// Auth state & flows: login/register/logout. After success we call checkMe() to capture the user and refresh the board.
// --- Auth state ---
const authedUser = ref(null)
const authMode = ref('login') // 'login' | 'register'
const authLoading = ref(false)
const authErr = ref('')
const loginEmail = ref('')
const loginPwd = ref('')
const regName = ref('')
const regEmail = ref('')
const regPwd = ref('')

async function checkMe(){
  try{
    const r = await apiFetch(`${API_BASE}/api/auth/me`)
    if (!r.ok) { authedUser.value = null; return }
    const u = await r.json()
    authedUser.value = u
    if (u?.id) setUserId(u.id)
  }catch{ authedUser.value = null }
}

async function doLogin(){
  authErr.value=''; authLoading.value=true
  try{
    const r = await apiFetch(`${API_BASE}/api/auth/login`, {
      method:'POST', headers:{ 'Content-Type':'application/json', 'X-CSRF-Token': getCsrf() },
      body: JSON.stringify({ email: loginEmail.value.trim(), password: loginPwd.value })
    })
    if(!r.ok) throw new Error(await r.text())
    await checkMe()
    if (authedUser.value) { notify('Signed in', 'success'); await load() }
  }catch(e){ authErr.value = String(e?.message || e) }
  finally{ authLoading.value=false }
}

async function doRegister(){
  authErr.value=''; authLoading.value=true
  try{
    const r = await apiFetch(`${API_BASE}/api/auth/register`, {
      method:'POST', headers:{ 'Content-Type':'application/json', 'X-CSRF-Token': getCsrf() },
      body: JSON.stringify({ name: regName.value.trim() || undefined, email: regEmail.value.trim(), password: regPwd.value })
    })
    if(!r.ok) throw new Error(await r.text())
    await checkMe()
    if (authedUser.value) { notify('Account created', 'success'); await load() }
  }catch(e){ authErr.value = String(e?.message || e) }
  finally{ authLoading.value=false }
}

async function doLogout(){
  try { await apiFetch(`${API_BASE}/api/auth/logout`, { method:'POST', headers:{ 'X-CSRF-Token': getCsrf() } }) } catch{}
  const uid = localStorage.getItem('logger.userId') || ''
  localStorage.removeItem('logger.userId')
  if (uid) localStorage.removeItem(`logger.runningEntry:${uid}`)
  authedUser.value = null
  notify('Signed out','success')
}

watch(authedUser, (u) => { if (u) load() })


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
let _extendHandle = null
async function stopRunningIfAny () {
  if (!runningId.value) return null
  const id = runningId.value
  try {
    const res = await apiFetch(`${API_BASE}/api/time-entries/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': getCsrf() },
      body: JSON.stringify({ end_utc: new Date().toISOString() })
    })
    if (!res.ok) notify(`Failed to stop timer: ${await res.text()}`, 'error')
  } catch (e) {
    notify(`Failed to stop timer: ${e?.message || e}`, 'error')
  } finally {
    if (_extendHandle) { clearInterval(_extendHandle); _extendHandle = null }
    setRunningId(null)
  }
  await load()
  return id
}
// Start a timer: stop any existing one, create a new entry with start_utc=now and a provisional end_utc (+1min),
// then extend end_utc every 30s while running. (This keeps duration visible even if the tab sleeps.)
async function startTimer (seedCard) {
  await stopRunningIfAny()
  const now = new Date()
  const inOneMin = new Date(now.getTime() + 60 * 1000)
  const payload = {
    // user_id: userId,
    project_code: seedCard.project_code || seedCard.projectCode || '',
    activity: seedCard.activity || '',
    start_utc: now.toISOString(),
    end_utc: inOneMin.toISOString(),
    notes: `[prio:${(seedCard.priority || 'Normal').toLowerCase()}]` + (seedCard.notes ? ` ${seedCard.notes}` : '')
  }
const res = await apiFetch(`${API_BASE}/api/time-entries/`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': getCsrf() },
  body: JSON.stringify(payload)
})
// ...
const created = await res.json()
setRunningId(created.id)

_extendHandle = setInterval(async () => {
  try {
    await apiFetch(`${API_BASE}/api/time-entries/${created.id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': getCsrf() },
      body: JSON.stringify({ end_utc: new Date().toISOString() })
    })
  } catch {}
}, 30000)
  await load()
  notify('Timer started', 'success')
}
async function stopTimer () {
  const id = await stopRunningIfAny()
  if (id) notify('Timer stopped', 'success')
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
  await checkMe()
  if (authedUser.value) {
    await loadProjects()
    await load()
    window.addEventListener('keydown', onKey)
  }
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
function laneMetaStorageKey(laneKey) { return `logger.laneMeta:${groupBy.value}:${laneKey}` }
function getLaneMeta(laneKey) {
  try { return JSON.parse(localStorage.getItem(laneMetaStorageKey(laneKey)) || '{}') } catch { return {} }
}
function setLaneMeta(laneKey, meta) { localStorage.setItem(laneMetaStorageKey(laneKey), JSON.stringify(meta || {})) }
function editLaneMeta(lane) {
  const current = getLaneMeta(lane.key)
  const desc = window.prompt('Project description:', current.description || '') ?? (current.description || '')
  const pri  = window.prompt('Priority (Low, Normal, High, Critical):', current.priority || 'Normal') ?? (current.priority || 'Normal')
  const normPri = (pri || 'Normal').trim()
  const valid = PRIORITIES.includes(normPri) ? normPri : 'Normal'
  setLaneMeta(lane.key, { description: desc, priority: valid })
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

// --- toasts ---
const toasts = ref([])
function notify(msg, type='info', ttl=3000){
  const id = Math.random().toString(36).slice(2)
  toasts.value.push({id,msg,type})
  setTimeout(()=>{ toasts.value = toasts.value.filter(t=>t.id!==id) }, ttl)
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
    jobTitle: e.project_code,
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
    const k = groupBy.value === 'project_code' ? (e.project_code || 'Ungrouped') : (e.activity || 'Ungrouped')
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
if (!ordered.length) ordered.push(buildEmptySwimlane('Ungrouped', 'Ungrouped'))


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
function customLanesKey() { return `logger.customLanes:${groupBy.value}` }
function loadCustomLanes() {
  try { return JSON.parse(localStorage.getItem(customLanesKey()) || '[]') } catch { return [] }
}
function saveCustomLanes(names) { localStorage.setItem(customLanesKey(), JSON.stringify(names)) }
function addLane() {
  const label = window.prompt(`Add ${groupBy.value === 'project_code' ? 'Project' : 'Activity'} name:`)?.trim()
  if (!label) return
  const exists = swimlanes.value.some(l => l.key === label || l.title === label)
  if (!exists) {
    const lane = buildEmptySwimlane(label, label)
    swimlanes.value = [lane, ...swimlanes.value]
  }
  const names = loadCustomLanes()
  if (!names.includes(label)) { names.push(label); saveCustomLanes(names) }
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
        start_utc: payload.start_utc,
        end_utc: payload.end_utc,
        notes: `[prio:${(payload.priority || 'Normal').toLowerCase()}]` + (payload.notes ? ` ${payload.notes}` : '')
      })
    })
    if (!res.ok) return notify(`Failed to update: ${await res.text()}`, 'error')
  } else {
    const res = await apiFetch(`${API_BASE}/api/time-entries/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': getCsrf() },
      body: JSON.stringify({
        // user_id: userId,
        project_code: payload.project_code || payload.projectCode,
        activity: payload.activity,
        start_utc: payload.start_utc,
        end_utc: payload.end_utc,
        notes: `[prio:${(payload.priority || 'Normal').toLowerCase()}]` + (payload.notes ? ` ${payload.notes}` : '')
      })
    })
    if (!res.ok) return notify(`Failed to create: ${await res.text()}`, 'error')
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
  if (!res.ok) return notify(`Failed to delete: ${await res.text()}`, 'error')
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
  <!-- Auth screen: simple email/password login/register forms. Cookies are set by the backend; we call checkMe() after. -->
      <section v-if="!authedUser" class="auth">
    <div class="auth__card">
      <h2>{{ authMode==='login' ? 'Sign in' : 'Create account' }}</h2>
      <form @submit.prevent="authMode==='login' ? doLogin() : doRegister()" class="auth__form">
        <label v-if="authMode==='register'">Name
          <input v-model="regName" />
        </label>
        <template v-if="authMode==='login'">
          <label>Email
            <input type="email" v-model="loginEmail" required autocomplete="username" />
          </label>
          <label>Password
            <input type="password" v-model="loginPwd" required autocomplete="current-password" />
          </label>
        </template>
        <template v-else>
          <label>Email
            <input type="email" v-model="regEmail" required autocomplete="username" />
          </label>
          <label>Password
            <input type="password" v-model="regPwd" required autocomplete="new-password" />
          </label>
        </template>
        <button :disabled="authLoading">{{ authLoading ? (authMode==='login' ? 'Signing in…' : 'Creating…') : (authMode==='login' ? 'Sign in' : 'Create account') }}</button>
        <p v-if="authErr" class="error">{{ authErr }}</p>
      </form>
      <p class="hint">
        <button class="link" @click="authMode = (authMode==='login' ? 'register' : 'login')">
          {{ authMode==='login' ? 'No account? Create one' : 'Have an account? Sign in' }}
        </button>
      </p>
    </div>
  </section>
  <section v-if="authedUser" class="board">
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
        <button type="button" @click="addLane">
          {{ groupBy === 'project_code' ? 'Add Project' : 'Add Activity' }}
        </button>
        <button type="button" @click="toggleTheme" :title="theme==='dark' ? 'Switch to Light' : 'Switch to Dark'">
          {{ theme==='dark' ? '☀︎' : '🌙' }}
        </button>
        <button type="button" @click="doLogout">Logout</button>
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
                <span v-if="getLaneMeta(pair.lane.key).priority"
                      class="badge"
                      :class="'p-' + (getLaneMeta(pair.lane.key).priority || 'Normal').toLowerCase()">
                  {{ getLaneMeta(pair.lane.key).priority }}
                </span>
              </div>
              <div class="lane-actions">
                <button class="mini icon"
                        @click="isLaneRunning(pair.lane) ? stopTimer() : startLaneTimer(pair.lane)"
                        :title="isLaneRunning(pair.lane) ? 'Stop timer' : 'Start timer'">
                  {{ isLaneRunning(pair.lane) ? '■' : '▶︎' }}
                </button>
              <button class="mini icon" @click="editLaneMeta(pair.lane)" title="Edit project settings">⋯</button>
                <button v-if="laneVisibleOnDayByProjects(pair.lane.key, pair.col.dayKey)" class="mini icon" @click="addCard(pair.lane, pair.col)" title="Add card">＋</button>
              </div>
            </div>
            <div v-if="getLaneMeta(pair.lane.key).description" class="focus__lanedesc">
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
      <div class="grid">
        <!-- Header row -->
        <div class="cell cell--head cell--rowhead"></div>
        <div v-for="d in headerDays" :key="d.key" class="cell cell--head">
          <div class="dayhead">
            <strong>{{ d.label }}</strong>
            <small>{{ fmtH(colHours(d.key), 2) }} h</small>
          </div>
        </div>

        <!-- Swimlane rows -->
        <template v-for="lane in swimlanes" :key="lane.key">
        <div class="cell cell--rowhead">
            <article class="projcard">
              <header class="projcard__head">
                <span
                  class="prio-dot"
                  :class="('p-' + (getLaneMeta(lane.key).priority || 'Normal').toLowerCase())"
                  :title="getLaneMeta(lane.key).priority || 'Normal'">
                </span>
                <h4 class="title" :title="lane.title">{{ lane.title }}</h4>
                <span class="hours">{{ fmtH(laneHours(lane), 2) }} h</span>
              </header>
            
              <section class="projcard__body">
                <p class="desc" :class="{ clamped: !isExpanded(lane.key) }" v-if="laneDesc(lane.key)">
                  {{ laneDesc(lane.key) }}
                </p>
                <button
                  v-if="isDescLong(lane.key)"
                  class="link more"
                  @click="toggleMoreDesc(lane.key)">
                  {{ isExpanded(lane.key) ? 'Show less' : 'Read more' }}
                </button>
              </section>
            
              <footer class="projcard__foot">
                <div class="spacer"></div>
                <div class="actions__icons">
                  <button class="mini icon"
                          @click="isLaneRunning(lane) ? stopTimer() : startLaneTimer(lane)"
                          :title="isLaneRunning(lane) ? 'Stop timer' : 'Start timer'">
                    {{ isLaneRunning(lane) ? '■' : '▶︎' }}
                  </button>
                  <button class="mini icon" @click="editLaneMeta(lane)" title="Edit project settings">⋯</button>
                </div>
              </footer>
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
  Knowledge Drop — Styles in this file
  - Board chrome: header/nav/toolbars and progress bar
  - Grid layout: weekly matrix cells, row headers, drag/drop styling
  - Focus (today) panel: expanded cards and plan textarea
  - Simple layout: lane columns with stacked entries and CTA when empty
  - Cards inside lists use :deep(.tcard) to tweak visuals without coupling to TimeCard internals
  Notes: keep selectors narrow; prefer utility blocks over deep nesting; respect the global CSS vars in App.vue.
*/
.board { max-width: var(--container); margin: 0 auto; padding: 12px; }
.board__header {
  display: grid; grid-template-columns: 1fr auto; align-items: center; gap: 12px;
  position: sticky; top: 0; z-index: 10; padding: 10px 0 12px; background: var(--bg);
  border-bottom: 1px solid var(--border);
}
.nav { display: flex; align-items: center; gap: 6px; }
.nav button {
  padding: .36rem .55rem;
  color: var(--primary);
  border: 1px solid var(--border);
  background: var(--btn-blue-bg);
  border-radius: 10px;
  cursor: pointer;
}
.nav button:hover { background: var(--btn-blue-bg-hover); }
.range { margin-left: .4rem; font-weight: 700; color: var(--text); }
.toolbar { display: flex; align-items: center; gap: 12px; }
.toolbar button {
  padding: .36rem .55rem;
  color: var(--primary);
  border: 1px solid var(--border);
  background: var(--btn-blue-bg);
  border-radius: 10px;
  cursor: pointer;
}
.toolbar button:hover { background: var(--btn-blue-bg-hover); }
/* Compact icon-sized buttons used for “…” and “＋” */
.mini {
  padding: .2rem .45rem;
  border: 1px solid var(--border);
  background: var(--btn-blue-bg);
  color: var(--primary);
  border-radius: 8px;
  cursor: pointer;
}
.mini:hover { background: var(--btn-blue-bg-hover); }
.mini.icon { padding:.2rem; width:28px; height:28px; display:inline-grid; place-items:center; border-radius:10px; }
.group { display: flex; align-items: center; gap: 6px; color: var(--muted); font-weight: 600; }
select { background: var(--panel); color: var(--text); border: 1px solid var(--border); border-radius: 8px; padding: .3rem .45rem; }
.goal { display: flex; align-items: center; gap: 8px; }
.goal .bar { width: 180px; height: 8px; border-radius: 999px; background: #e2e8f0; overflow: hidden; border: 1px solid var(--border); }
.goal .bar i { display: block; height: 100%; background: linear-gradient(90deg, var(--primary), var(--accent)); }
.goal span { color: var(--muted); font-weight: 700; }

/* Scroller remains for very small viewports, but 7 cols fit at typical widths */
.board__scroller { overflow: auto; padding-bottom: 8px; }
.grid {
  --rowhead-w: 160px;
  display: grid;
  grid-template-columns: var(--rowhead-w) repeat(7, 1fr);
  gap: 8px;
  align-items: start;
  padding: 8px 0;
}
.cell {
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  min-height: 100px;
  position: relative;
}
.cell--head { background: transparent; border: none; min-height: auto; }
.cell--rowhead { position: sticky; left: 0; z-index: 5; background: var(--panel); border-right: 1px solid var(--border); }
.cell__empty { pointer-events: none; }
.dayhead { display: flex; align-items: baseline; justify-content: space-between; padding: 8px 6px; border-bottom: 1px solid var(--border); color: var(--muted); font-weight: 700; font-size: .95rem; }
.lanehead { display: flex; align-items: baseline; justify-content: space-between; padding: 10px 8px; font-weight: 700; font-size: .95rem; }
.lanehead__title { display: flex; align-items: center; gap: 6px; }
.lanehead__right { display: flex; align-items: center; gap: 6px; }
.lanehead__desc { color: var(--muted); font-size: .85rem; padding: 0 8px 8px; }
/* Prevent rowhead contents from bleeding into the first day column */
.cell--rowhead { overflow: hidden; }
.lanehead { gap: 8px; }
.lanehead__title { min-width: 0; }
.lanehead__title strong {
  display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.lanehead__desc { overflow-wrap: anywhere; word-break: break-word; }
.lanehead__right { flex-shrink: 0; }

.badge { font-size: .72rem; padding: .1rem .45rem; border-radius: 999px; border: 1px solid var(--border); }
.badge.p-low { background: #eef6ff; color: #1e3a8a; }
.badge.p-normal { background: #eef2ff; color: #3730a3; }
.badge.p-high { background: #fff7ed; color: #9a3412; border-color: #fed7aa; }
.badge.p-critical { background: #fef2f2; color: #991b1b; border-color: #fecaca; }

.cell__sum { position: absolute; top: 6px; left: 6px; font-size: .78rem;
             padding: .1rem .35rem; background: #edf2ff; border: 1px solid var(--border);
             border-radius: 8px; color: #1e3a8a; }

.focus__lanedesc { color: var(--muted); font-size: .85rem; padding: 6px 10px 0; }
.cell__actions { position: absolute; top: 6px; right: 6px; }
.cell__actions .mini { font-size: 16px; padding: .15rem .45rem; line-height: 1.1; }

.droplist { display: grid; gap: 8px; padding: 8px; max-height: calc(100vh - 220px); overflow: auto; }
/* Ensure TimeCard surfaces inside cells look like cards and don't “blend” into the cell */
.droplist :deep(.tcard){ background:#fff; border-color:#cbd5e1; box-shadow:var(--shadow-sm); overflow:hidden; }
/* Drag classes for better feedback */
:global(.drag-ghost)    { opacity: .6; transform: rotate(2deg); }
:global(.drag-chosen)   { box-shadow: var(--shadow-md) !important; }
:global(.drag-dragging) { cursor: grabbing; }

.error { color: #b91c1c; }

/* --- Focus (enlarged current-day column) --- */
.focus { width: 100%; margin: 12px 0 16px; background: var(--panel); border: 1px solid var(--border); border-radius: var(--radius); box-shadow: var(--shadow-sm); }
.focus--inboard { max-width: 100%; }
.focus__header { display: flex; justify-content: space-between; align-items: baseline; padding: 12px 14px; border-bottom: 1px solid var(--border); }
.focus__hours { color: var(--muted); font-weight: 700; }
.focus__layout { position: relative; display: grid; align-items: start; grid-template-columns: 340px 1fr; gap: 16px; padding: 12px; }
@media (max-width: 1100px) { .focus__layout { grid-template-columns: 1fr; } }
.focus__plan { display: grid; gap: 8px; position: sticky; top: 0; align-self: start; z-index: 0;}
.focus__label { font-weight: 700; color: var(--muted); display: block; margin-bottom: .5rem;}
.focus__textarea { width: 100%; min-height: 160px; resize: vertical; padding: .6rem .7rem; border: 1px solid var(--border); border-radius: 10px; background: var(--panel-2); color: var(--text); }
.focus__hint { color: var(--muted); }
.focus__col { display: grid; gap: 12px; position: relative; z-index: 1;}
.focus__lane { background: var(--panel); border: 1px solid var(--border); border-radius: 10px; }
.focus__lanehead { display: flex; align-items: center; justify-content: space-between; padding: 8px 10px; border-bottom: 1px solid var(--border); font-weight: 700; }
.focus__droplist { display: grid; gap: 10px; padding: 10px; max-height: none; position: relative; z-index: 1;}
.focus :deep(.tcard) { box-shadow: var(--shadow-md); }

.toastbox{ position:sticky; top:8px; z-index:20; display:grid; gap:6px; justify-items:end; }
.toast{ background:var(--panel); border:1px solid var(--border); color:var(--text); padding:.45rem .6rem; border-radius:10px; box-shadow:var(--shadow-sm); }
.toast.success{ border-color:#16a34a; }
.toast.error{ border-color:#ef4444; }

/* Compact project card shown in the left row header */
.projcard{
  display:grid; grid-template-rows:auto 1fr auto;
  gap:8px; background:var(--panel); border-radius:10px; padding:10px;
  min-height:110px;
}
.projcard__head{
  display:grid; grid-template-columns:auto 1fr auto;
  align-items:center; gap:8px;
}
.projcard__head .title{
  margin:0; font-size:.98rem; font-weight:800;
  overflow:hidden; text-overflow:ellipsis; white-space:nowrap;
}
.projcard__head .hours{ color:var(--muted); font-weight:700; }
/* Hide project description in weekly grid row header */
.projcard__body { display: none; }
.projcard__body .desc{ color:var(--muted); margin:0; }
.projcard__body .desc.clamped{
  display:-webkit-box; -webkit-box-orient:vertical; overflow:hidden;
}
.projcard__foot{ display:flex; justify-content:flex-end; gap:.35rem; }
.projcard .link.more{
  background:transparent; border:none; color:var(--primary);
  padding:0; cursor:pointer;
}

/* color-only priority dot (same palette as TimeCard) */
.prio-dot { width:10px; height:10px; border-radius:999px; display:inline-block; border:1px solid var(--border); }
.prio-dot.p-low { background:#93c5fd; border-color:#93c5fd; }
.prio-dot.p-normal { background:#a5b4fc; border-color:#a5b4fc; }
.prio-dot.p-high { background:#fdba74; border-color:#fdba74; }
.prio-dot.p-critical { background:#fca5a5; border-color:#fca5a5; }


/* --- Simple layout styles (cardy) --- */
.simple { display: grid; gap: 16px; margin-top: 12px; }

/* Day chips */
.simple__days {
  display: flex; gap: 8px; flex-wrap: wrap;
  position: sticky; top: 64px; z-index: 2;
}
.simple__daybtn {
  display: inline-flex; align-items: baseline; gap: 6px;
  border: 1px solid var(--border);
  background: var(--panel);
  color: var(--text);
  border-radius: 999px;
  padding: .35rem .7rem;
  cursor: pointer;
  box-shadow: var(--shadow-sm);
}
.simple__daybtn.active { background: var(--btn-blue-bg); }

/* Projects/activities as columns */
.simple__lanes {
  display: grid;
  grid-auto-flow: column;              /* lay lanes side-by-side as columns */
  grid-auto-columns: minmax(260px, 1fr); /* each lane column width */
  gap: 16px;
  align-items: start;
  overflow-x: auto;                    /* scroll horizontally if many lanes */
  padding-bottom: 4px;
}
.simple__lane {
  display: grid;
  grid-template-rows: auto 1fr;  /* header + entries take remaining height */
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 14px;
  box-shadow: var(--shadow-sm);
  min-height: 280px;
}
.simple__lanehead { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
.simple__lanehead .title { margin: 0; font-size: 1.05rem; }
.simple__lanehead .right { display: inline-flex; gap: 6px; align-items: center; }
.badge.hours { background: var(--btn-blue-bg); border: 1px solid var(--border); }

/* Entries container: vertical stack within each lane column */
.simple__entries { display: grid; grid-template-rows: 1fr; }
.simple__droplist {
  display: grid;
  gap: 12px;
  grid-template-columns: 1fr;   /* single column of entry cards */
  align-items: start;
  overflow-y: auto;
  max-height: 60vh;              /* keep columns tidy; adjust as needed */
}

/* Keep each TimeCard looking like a small card */
.simple__droplist :deep(.tcard) {
  background: var(--panel);
  border-color: var(--border);
  box-shadow: var(--shadow-sm);
  border-radius: 10px;
  min-height: 64px;
}

/* --- Auth screen --- */
.auth { max-width: 520px; margin: 2rem auto; padding: 1rem; }
.auth__card { border: 1px solid var(--border); border-radius: 12px; padding: 1rem; background: var(--panel); box-shadow: var(--shadow-sm); }
.auth__form { display: grid; gap: .6rem; margin-top: .5rem; }
.auth__form label { display: grid; gap: .25rem; }
.auth input { padding: .5rem .6rem; border: 1px solid var(--border); border-radius: 8px; background: var(--panel-2); color: var(--text); }
.auth input::placeholder { color: color-mix(in srgb, var(--muted) 70%, transparent); }
.auth input:focus { outline: 2px solid color-mix(in srgb, var(--primary) 60%, transparent); }
.auth button { padding: .5rem .8rem; border: 1px solid var(--border); border-radius: 8px; cursor: pointer; }
.auth .hint { margin-top: .6rem; }
.auth .link { background: transparent; border: none; color: var(--primary); cursor: pointer; padding: 0; }
</style>