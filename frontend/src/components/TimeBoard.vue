<script setup>
import { ref, onMounted, computed, watch } from 'vue'
import draggable from 'vuedraggable'
import TimeCard from './TimeCard.vue'
import { onUnmounted } from 'vue'

// --- Global ticking for live timers ---
const nowTick = ref(Date.now())
let _nowHandle = null
onMounted(() => {
  _nowHandle = setInterval(() => (nowTick.value = Date.now()), 1000)
})
onUnmounted(() => { if (_nowHandle) clearInterval(_nowHandle) })

// --- Running timer pointer (client-side) ---
function runningKey () { return `logger.runningEntry:${userId}` }
const runningId = ref(localStorage.getItem(runningKey()))
function setRunningId (id) {
  runningId.value = id
  if (id) localStorage.setItem(runningKey(), id)
  else localStorage.removeItem(runningKey())
}
let _extendHandle = null
async function stopRunningIfAny () {
  if (!runningId.value) return null
  const id = runningId.value
  try {
    const res = await fetch(`${API_BASE}/api/time-entries/${id}`, {
      method: 'PATCH', headers: { 'Content-Type': 'application/json' },
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
async function startTimer (seedCard) {
  await stopRunningIfAny()
  const now = new Date()
  const inOneMin = new Date(now.getTime() + 60 * 1000)
  const payload = {
    user_id: userId,
    project_code: seedCard.project_code || seedCard.projectCode || '',
    activity: seedCard.activity || '',
    start_utc: now.toISOString(),
    end_utc: inOneMin.toISOString(),
    notes: `[prio:${(seedCard.priority || 'Normal').toLowerCase()}]` + (seedCard.notes ? ` ${seedCard.notes}` : '')
  }
  const res = await fetch(`${API_BASE}/api/time-entries/`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  })
  if (!res.ok) {
    return notify(`Failed to start timer: ${await res.text()}`, 'error')
  }
  const created = await res.json()
  setRunningId(created.id)
  // Periodically extend end_utc so duration grows while the tab is open
  _extendHandle = setInterval(async () => {
    try {
      await fetch(`${API_BASE}/api/time-entries/${created.id}`, {
        method: 'PATCH', headers: { 'Content-Type': 'application/json' },
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

onMounted(() => { load(); window.addEventListener('keydown', onKey) })
onUnmounted(() => window.removeEventListener('keydown', onKey))

const API_BASE = import.meta.env.VITE_API_BASE || 'http://127.0.0.1:8000'
const userId = 'user-123' // TODO: wire real auth later
const TARGET_WEEKLY_HOURS = 40

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

// ---- Date helpers (local time) ----
function pad(n) { return String(n).padStart(2, '0') }
function startOfWeek(d = new Date()) {
  const day = d.getDay() || 7  // Sun=0 -> 7
  const monday = new Date(d)
  monday.setHours(0,0,0,0)
  monday.setDate(d.getDate() - (day - 1))
  return monday
}
function addDays(d, n) { const z = new Date(d); z.setDate(z.getDate() + n); return z }
function dateKey(d) { return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}` }
function labelFor(d) { return d.toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' }) }
function laneKeyFromISO(iso) { if (!iso) return null; return dateKey(new Date(iso)) }
function timeHMFromISO(iso) { const d = new Date(iso); return `${pad(d.getHours())}:${pad(d.getMinutes())}` }
function composeISOFromLaneAndTime(laneKey, hm) {
  const local = new Date(`${laneKey}T${hm}`) // local time
  return local.toISOString() // store UTC
}
function hoursBetween(isoA, isoB) {
  if (!isoA || !isoB) return 0
  const a = new Date(isoA).getTime()
  const b = new Date(isoB).getTime()
  return Math.max(0, (b - a) / 3600000)
}

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

// ---- Grouping (rows) ----
const GROUPS = [
  { value: 'project_code', label: 'Project' },
  { value: 'activity', label: 'Activity' },
]
const groupBy = ref('project_code')

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

async function load() {
  loading.value = true; error.value = ''
  try {
    const monday = currentWeekStart.value
    const nextMonday = addDays(monday, 7)
    const qs = new URLSearchParams({ user_id: userId, from: monday.toISOString(), to: nextMonday.toISOString() }).toString()
    const res = await fetch(`${API_BASE}/api/time-entries/?${qs}`)
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
    const res = await fetch(`${API_BASE}/api/time-entries/${payload.id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
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
   const res = await fetch(`${API_BASE}/api/time-entries/`, {
     method: 'POST',
     headers: { 'Content-Type': 'application/json' },
     body: JSON.stringify({
       user_id: userId,
       project_code: payload.project_code || payload.projectCode,
       activity: payload.activity,
       start_utc: payload.start_utc,
       end_utc: payload.end_utc,
       notes: `[prio:${(payload.priority || 'Normal').toLowerCase()}]` + (payload.notes ? ` ${payload.notes}` : '')
     })
   })
    if (!res.ok) return notify(`Failed to update: ${await res.text()}`, 'error')
  }
  await load()
}

async function deleteCard(lane, col, card) {
  if (!card.id || String(card.id).startsWith('tmp_')) {
    col.cards = col.cards.filter(c => c !== card)
    return
  }
  const res = await fetch(`${API_BASE}/api/time-entries/${card.id}`, { method: 'DELETE' })
  if (!res.ok) return notify(`Failed to update: ${await res.text()}`, 'error')
  await load()
}

function addCard(lane, col) {
  const now = new Date()
  const hm = `${pad(now.getHours())}:${pad(now.getMinutes())}`
  const startLocal = new Date(`${col.dayKey}T${hm}`)
  const endLocal   = new Date(startLocal.getTime() + 30 * 60000)

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
function onCellChange(lane, col, evt) {
  if (evt?.added) {
    const card = evt.added.element
    const startHM = timeHMFromISO(card.start_utc || new Date().toISOString())
    const endHM   = timeHMFromISO(card.end_utc || startHM)
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
function colHours(dayKey) {
  let sum = 0
  for (const lane of swimlanes.value) {
    const col = lane.columns.find(c => c.dayKey === dayKey)
    if (col) sum += col.cards.reduce((s, c) => s + hoursBetween(c.start_utc, c.end_utc), 0)
  }
  return sum
}
function laneHours(lane) {
  return lane.columns.reduce((tot, c) => tot + c.cards.reduce((s, x) => s + hoursBetween(x.start_utc, x.end_utc), 0), 0)
}
function cellHours(lane, dayKey) {
  const col = lane.columns.find(c => c.dayKey === dayKey)
  if (!col) return 0
  return col.cards.reduce((s, c) => s + hoursBetween(c.start_utc, c.end_utc), 0)
}
const weeklyHours = computed(() => headerDays.value.reduce((tot, d) => tot + colHours(d.key), 0))
const weeklyPct = computed(() => Math.min(1, (TARGET_WEEKLY_HOURS ? (weeklyHours.value / TARGET_WEEKLY_HOURS) : 0)))
const todayLabel = computed(() => todayHeader.value ? todayHeader.value.label : '')

// ---- Focus: enlarge the current day's column at the top ----
const isSameDay = (a, b) => a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate()
const todayHeader = computed(() => headerDays.value.find(d => isSameDay(d.date, new Date())))
const todayKey = computed(() => todayHeader.value?.key || null)
const showFocus = computed(() => !!todayKey.value && isSameDay(currentWeekStart.value, startOfWeek(new Date())))

// Per-day plan note (local persistence for now; can be moved to backend later)
const dailyPlan = ref('')
function planKey(dayKey) { return `logger.dailyPlan:${userId}:${dayKey}` }
watch(todayKey, (k) => { if (k) dailyPlan.value = localStorage.getItem(planKey(k)) || '' }, { immediate: true })
watch(dailyPlan, (v) => { const k = todayKey.value; if (k != null) localStorage.setItem(planKey(k), v) })

// Aggregate today's cards across all swimlanes
const todayLanes = computed(() => {
  if (!todayKey.value) return []
  return swimlanes.value.map(lane => ({
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
        <div class="goal">
          <div class="bar"><i :style="{ width: (weeklyPct*100)+'%' }"></i></div>
          <span>{{ weeklyHours.toFixed(1) }} / {{ TARGET_WEEKLY_HOURS }} h</span>
        </div>
        <button type="button" @click="addLane">
          {{ groupBy === 'project_code' ? 'Add Project' : 'Add Activity' }}
        </button>
      </div>
    </header>
    <section v-if="showFocus" class="focus focus--inboard">
      <header class="focus__header">
        <strong>Today — {{ todayLabel }}</strong>
        <span class="focus__hours">{{ colHours(todayKey).toFixed(1) }} h</span>
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
          <small class="focus__hint">Saved locally for now</small>
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
                <button class="mini icon" @click="editLaneMeta(pair.lane)" title="Edit project settings">⋯</button>
                <button class="mini icon" @click="addCard(pair.lane, pair.col)" title="Add card">＋</button>
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
    <div class="board__scroller">
      <div class="grid">
        <!-- Header row -->
        <div class="cell cell--head cell--rowhead"></div>
        <div v-for="d in headerDays" :key="d.key" class="cell cell--head">
          <div class="dayhead">
            <strong>{{ d.label }}</strong>
            <small>{{ colHours(d.key).toFixed(1) }} h</small>
          </div>
        </div>

        <!-- Swimlane rows -->
        <template v-for="lane in swimlanes" :key="lane.key">
          <!-- Row header cell -->
          <div class="cell cell--rowhead">
            <div class="lanehead">
              <div class="lanehead__title">
                <strong>{{ lane.title }}</strong>
                <span v-if="getLaneMeta(lane.key).priority"
                      class="badge"
                      :class="'p-' + (getLaneMeta(lane.key).priority || 'Normal').toLowerCase()">
                  {{ getLaneMeta(lane.key).priority }}
                </span>
              </div>
              <div class="lanehead__right">
                <small>{{ laneHours(lane).toFixed(1) }} h</small>
                <button class="mini icon" @click="editLaneMeta(lane)" title="Edit project settings">⋯</button>
              </div>
            </div>
            <div v-if="getLaneMeta(lane.key).description" class="lanehead__desc">
              {{ getLaneMeta(lane.key).description }}
            </div>
          </div>

          <!-- Day cells -->
          <template v-for="col in lane.columns" :key="lane.key + ':' + col.dayKey">
            <div class="cell">
              <div class="cell__sum" v-if="cellHours(lane, col.dayKey)">{{ cellHours(lane, col.dayKey).toFixed(1) }} h</div>
              <div class="cell__actions">
                <button class="mini icon" @click="addCard(lane, col)" title="Add card to this cell">＋</button>
              </div>
              <div v-if="!col.cards.length" class="cell__empty">No entries</div>
              <draggable
                v-model="col.cards"
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
                            :running-id="runningId" :now-tick="nowTick"
                            @start="startTimer" @stop="stopTimer"
                            @save="saveCard" @delete="c => deleteCard(lane, col, c)" />
                </template>
              </draggable>
            </div>
          </template>
        </template>
      </div>
    </div>
  </section>
</template>

<style scoped>
.board { max-width: var(--container); margin: 0 auto; padding: 12px; }
.board__header {
  display: grid; grid-template-columns: 1fr auto; align-items: center; gap: 12px;
  position: sticky; top: 0; z-index: 10; padding: 10px 0 12px; background: var(--bg);
  border-bottom: 1px solid var(--border);
}
.nav { display: flex; align-items: center; gap: 6px; }
.nav button {
  padding: .36rem .55rem;
  color: rgb(25, 40, 209);
  border: 1px solid var(--border);
  background: var(--btn-blue-bg);      /* was var(--panel) */
  border-radius: 10px;
  cursor: pointer;
}
.nav button:hover { background: var(--btn-blue-bg-hover); }
.range { margin-left: .4rem; font-weight: 700; color: var(--text); }
.toolbar { display: flex; align-items: center; gap: 12px; }
.toolbar button {
  padding: .36rem .55rem;
  color: rgb(25, 40, 209);
  border: 1px solid var(--border);
  background: var(--btn-blue-bg);      /* was var(--panel) */
  border-radius: 10px;
  cursor: pointer;
}
.toolbar button:hover { background: var(--btn-blue-bg-hover); }
/* Compact icon-sized buttons used for “…” and “＋” */
.mini {
  padding: .2rem .45rem;
  border: 1px solid var(--border);
  background: var(--btn-blue-bg);
  color: rgb(25, 40, 209);
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
  --rowhead-w: 160px;            /* compact row header */
  display: grid;
  grid-template-columns: var(--rowhead-w) repeat(7, 1fr); /* always fits container width */
  gap: 8px;                      /* tighter gaps */
  align-items: start;
  padding: 8px 0;
}
.cell {
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  min-height: 100px;             /* slightly shorter cells */
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
.cell--rowhead { overflow: hidden; }                /* clip to the rowhead cell */
.lanehead { gap: 8px; }                             /* breathing room */
.lanehead__title { min-width: 0; }                  /* allow flex child to shrink */
.lanehead__title strong {
  display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.lanehead__desc { overflow-wrap: anywhere; word-break: break-word; }  /* safe wrapping */
.lanehead__right { flex-shrink: 0; }                /* keep the … button inside the cell */

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
.focus__layout { display: grid; grid-template-columns: 340px 1fr; gap: 16px; padding: 12px; }
@media (max-width: 1100px) { .focus__layout { grid-template-columns: 1fr; } }
.focus__plan { display: grid; gap: 8px; }
.focus__label { font-weight: 700; color: var(--muted); }
.focus__textarea { width: 100%; min-height: 160px; resize: vertical; padding: .6rem .7rem; border: 1px solid var(--border); border-radius: 10px; background: var(--panel-2); color: var(--text); }
.focus__hint { color: var(--muted); }
.focus__col { display: grid; gap: 12px; }
.focus__lane { background: var(--panel); border: 1px solid var(--border); border-radius: 10px; }
.focus__lanehead { display: flex; align-items: center; justify-content: space-between; padding: 8px 10px; border-bottom: 1px solid var(--border); font-weight: 700; }
.focus__droplist { display: grid; gap: 10px; padding: 10px; max-height: none; }
.focus :deep(.tcard) { box-shadow: var(--shadow-md); }

.toastbox{ position:sticky; top:8px; z-index:20; display:grid; gap:6px; justify-items:end; }
.toast{ background:var(--panel); border:1px solid var(--border); color:var(--text); padding:.45rem .6rem; border-radius:10px; box-shadow:var(--shadow-sm); }
.toast.success{ border-color:#16a34a; }
.toast.error{ border-color:#ef4444; }
</style>
