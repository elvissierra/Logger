<script setup>
import { ref, onMounted, computed, watch } from 'vue'
import draggable from 'vuedraggable'
import TimeCard from './TimeCard.vue'

const API_BASE = import.meta.env.VITE_API_BASE || 'http://127.0.0.1:8000'
const userId = 'user-123' // TODO: wire real auth later
const TARGET_WEEKLY_HOURS = 40

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

function mapEntryToCard(e) {
  return {
    id: e.id,
    jobTitle: e.project_code,     // provisional display
    projectCode: e.project_code,
    activity: e.activity,
    description: '',
    notes: e.notes || '',
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

  if (lanesMap.size === 0) lanesMap.set('Ungrouped', buildEmptySwimlane('Ungrouped', 'Ungrouped'))

  swimlanes.value = Array.from(lanesMap.values())
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

// Create / Update / Delete
async function saveCard(payload) {
  if (payload.id && String(payload.id).startsWith('tmp_')) payload.id = null

  if (payload.id) {
    const res = await fetch(`${API_BASE}/api/time-entries/${payload.id}`, {
      method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({
        project_code: payload.project_code || payload.projectCode,
        activity: payload.activity,
        start_utc: payload.start_utc,
        end_utc: payload.end_utc,
        notes: payload.notes
      })
    })
    if (!res.ok) return alert(`Failed to update: ${await res.text()}`)
  } else {
    const res = await fetch(`${API_BASE}/api/time-entries/`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({
        user_id: userId,
        project_code: payload.project_code || payload.projectCode,
        activity: payload.activity,
        start_utc: payload.start_utc,
        end_utc: payload.end_utc,
        notes: payload.notes
      })
    })
    if (!res.ok) return alert(`Failed to create: ${await res.text()}`)
  }
  await load()
}

async function deleteCard(lane, col, card) {
  if (!card.id || String(card.id).startsWith('tmp_')) {
    col.cards = col.cards.filter(c => c !== card)
    return
  }
  const res = await fetch(`${API_BASE}/api/time-entries/${card.id}`, { method: 'DELETE' })
  if (!res.ok) return alert(`Failed to delete: ${await res.text()}`)
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
const weeklyHours = computed(() => headerDays.value.reduce((tot, d) => tot + colHours(d.key), 0))
const weeklyPct = computed(() => Math.min(1, weeklyHours.value / TARGET_WEEKLY_HOURS))

// Effects
onMounted(load)
watch([currentWeekStart, groupBy], () => { load() })
</script>

<template>
  <section class="board">
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
      </div>
    </header>

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
              <strong>{{ lane.title }}</strong>
              <small>{{ laneHours(lane).toFixed(1) }} h</small>
            </div>
          </div>

          <!-- Day cells -->
          <template v-for="col in lane.columns" :key="lane.key + ':' + col.dayKey">
            <div class="cell">
              <div class="cell__actions">
                <button class="mini" @click="addCard(lane, col)" title="Add card to this cell">＋</button>
              </div>
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
                  <TimeCard :card="element" @save="saveCard" @delete="c => deleteCard(lane, col, c)" />
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
  padding: .36rem .55rem; color:rgb(25, 40, 209); border: 1px solid var(--border); background: var(--panel); border-radius: 10px; cursor: pointer;
}
.range { margin-left: .4rem; font-weight: 700; color: var(--text); }
.toolbar { display: flex; align-items: center; gap: 12px; }
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

.dayhead { display: flex; align-items: baseline; justify-content: space-between; padding: 8px 6px; border-bottom: 1px solid var(--border); color: var(--muted); font-weight: 700; font-size: .95rem; }
.lanehead { display: flex; align-items: baseline; justify-content: space-between; padding: 10px 8px; position: sticky; left: 0; font-weight: 700; font-size: .95rem; }

.cell__actions { position: absolute; top: 6px; right: 6px; }
.cell__actions .mini { font-size: 16px; padding: 0 .35rem; line-height: 1.1; border-radius: 8px; background: var(--panel-2); border: 1px solid var(--border); cursor: pointer; color: var(--text); }
.cell__actions .mini:hover { background: #394860; }

.droplist { display: grid; gap: 8px; padding: 8px; max-height: calc(100vh - 220px); overflow: auto; }

/* Drag classes for better feedback */
:global(.drag-ghost)    { opacity: .6; transform: rotate(2deg); }
:global(.drag-chosen)   { box-shadow: var(--shadow-md) !important; }
:global(.drag-dragging) { cursor: grabbing; }

.error { color: #b91c1c; }
</style>