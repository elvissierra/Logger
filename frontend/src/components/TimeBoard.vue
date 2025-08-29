<script setup>
import { ref, onMounted, computed } from 'vue'
import draggable from 'vuedraggable'
import TimeCard from './TimeCard.vue'

const API_BASE = import.meta.env.VITE_API_BASE || 'http://127.0.0.1:8000'
const userId = 'user-123' // TODO: wire real auth later

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
function timeHMFromISO(iso) {
  const d = new Date(iso)
  return `${pad(d.getHours())}:${pad(d.getMinutes())}`
}
function composeISOFromLaneAndTime(laneKey, hm) {
  // laneKey: YYYY-MM-DD, hm: HH:MM interpreted in local time
  const local = new Date(`${laneKey}T${hm}`)
  return local.toISOString() // convert to UTC ISO
}
function hoursBetween(isoA, isoB) {
  if (!isoA || !isoB) return 0
  const a = new Date(isoA).getTime()
  const b = new Date(isoB).getTime()
  return Math.max(0, (b - a) / 3600000)
}

// ---- State ----
const lanes = ref([]) // [{ key, date, label, cards: [] }]
const loading = ref(false)
const error = ref('')

// Build current week (Mon–Sun)
function buildWeek() {
  const monday = startOfWeek(new Date())
  const arr = []
  for (let i = 0; i < 7; i++) {
    const d = addDays(monday, i)
    arr.push({ key: dateKey(d), date: d, label: labelFor(d), cards: [] })
  }
  lanes.value = arr
}
function clearLaneCards() { for (const lane of lanes.value) lane.cards = [] }

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
function assignCardsToLanes(entries) {
  clearLaneCards()
  const byKey = new Map(lanes.value.map(l => [l.key, l]))
  for (const e of entries) {
    const k = laneKeyFromISO(e.start_utc)
    const lane = byKey.get(k)
    if (lane) lane.cards.push(mapEntryToCard(e))
  }
  applyLocalOrder()
}

async function load() {
  loading.value = true; error.value = ''
  try {
    const res = await fetch(`${API_BASE}/api/time-entries/`)
    if (!res.ok) throw new Error(await res.text())
    assignCardsToLanes(await res.json())
  } catch (e) {
    error.value = String(e)
  } finally {
    loading.value = false
  }
}

// Persist order per lane
function onReorder(lane) {
  localStorage.setItem(`logger.cardOrder:${lane.key}`, JSON.stringify(lane.cards.map(c => c.id)))
}
function applyLocalOrder() {
  for (const lane of lanes.value) {
    const order = JSON.parse(localStorage.getItem(`logger.cardOrder:${lane.key}`) || '[]')
    if (!order.length) continue
    const byId = new Map(lane.cards.map(c => [c.id, c]))
    const reordered = []
    for (const id of order) if (byId.has(id)) reordered.push(byId.get(id))
    for (const c of lane.cards) if (!order.includes(c.id)) reordered.push(c)
    lane.cards = reordered
  }
}

function ensureTempId(card) {
  if (!card.id) {
    card.id = (crypto?.randomUUID?.() || `tmp_${Date.now()}_${Math.random().toString(16).slice(2)}`)
  }
}

async function saveCard(payload) {
  // If this is a new unsaved card, force a POST
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
        notes: payload.notes
      })
    })
    if (!res.ok) return alert(`Failed to update: ${await res.text()}`)
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
        notes: payload.notes
      })
    })
    if (!res.ok) return alert(`Failed to create: ${await res.text()}`)
  }
  await load()
}

async function deleteCard(lane, card) {
  if (!card.id || String(card.id).startsWith('tmp_')) {
    lane.cards = lane.cards.filter(c => c !== card)
    return
  }
  const res = await fetch(`${API_BASE}/api/time-entries/${card.id}`, { method: 'DELETE' })
  if (!res.ok) return alert(`Failed to delete: ${await res.text()}`)
  await load()
}

function addCard(lane) {
  const now = new Date()
  const hm = `${String(now.getHours()).padStart(2,'0')}:${String(now.getMinutes()).padStart(2,'0')}`

  // Default new card to a 30-minute duration
  const startLocal = new Date(`${lane.key}T${hm}`)       // local time
  const endLocal   = new Date(startLocal.getTime() + 30 * 60000)

  const card = {
    id: (crypto?.randomUUID?.() || `tmp_${Date.now()}_${Math.random().toString(16).slice(2)}`),
    jobTitle: '',
    projectCode: '',
    activity: '',
    description: '',
    notes: '',
    start_utc: startLocal.toISOString(),
    end_utc: endLocal.toISOString()
  }
  lane.cards.unshift(card)
}

// Fired on cross-lane and in-lane changes
function onLaneChange(lane, evt) {
  if (evt?.added) {
    const card = evt.added.element
    // Adjust date to target lane, keep the time-of-day
    const startHM = timeHMFromISO(card.start_utc || new Date().toISOString())
    const endHM   = timeHMFromISO(card.end_utc || startHM)
    card.start_utc = composeISOFromLaneAndTime(lane.key, startHM)
    card.end_utc   = composeISOFromLaneAndTime(lane.key, endHM)

    // Persist only if this card already exists on the server
    if (card.id && !String(card.id).startsWith('tmp_')) {
      saveCard(card)
    }
  }
  onReorder(lane)
}

// Totals
function laneHours(lane) {
  return lane.cards.reduce((sum, c) => sum + hoursBetween(c.start_utc, c.end_utc), 0)
}
const weeklyHours = computed(() => lanes.value.reduce((a, l) => a + laneHours(l), 0))

onMounted(() => { buildWeek(); load() })
</script>

<template>
  <section class="board">
    <header class="board__header">
      <h1>Week</h1>
      <div class="totals"><strong>Weekly Total: {{ weeklyHours.toFixed(2) }} h</strong></div>
    </header>

    <p v-if="error" class="error">{{ error }}</p>
    <p v-if="loading">Loading…</p>

    <div class="lanes">
      <div v-for="lane in lanes" :key="lane.key" class="lane">
        <div class="lane__header">
          <div class="lane__title">{{ lane.label }}</div>
          <div class="lane__hours">{{ laneHours(lane).toFixed(2) }} h</div>
          <button class="lane__add" type="button" @click="addCard(lane)">+ Add</button>
        </div>

        <draggable
          v-model="lane.cards"
          item-key="id"
          :animation="200"
          handle=".handle"
          class="lane__list"
          :group="{ name: 'cards', pull: true, put: true }"
          @change="onLaneChange(lane, $event)"
          @end="onReorder(lane)"
        >
          <template #item="{ element }">
            <TimeCard :card="element" @save="saveCard" @delete="c => deleteCard(lane, c)" />
          </template>
        </draggable>
      </div>
    </div>
  </section>
</template>

<style scoped>
.board { max-width: 1200px; margin: 2rem auto; padding: 0 1rem; }
.board__header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 1rem; }
.totals { font-size: .95rem; color: #111827; }
.lanes {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: .8rem;
  align-items: start;
}
.lane {
  background: #f9fafb;
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  padding: .5rem;
  min-height: 120px;
}
.lane__header {
  display: grid;
  grid-template-columns: 1fr auto auto;
  align-items: center;
  gap: .4rem;
  margin-bottom: .5rem;
}
.lane__title { font-weight: 600; }
.lane__hours { font-size: .9rem; color: #374151; }
.lane__add {
  padding: .35rem .55rem; border: 1px solid #d1d5db; border-radius: 8px; background: #fff; cursor: pointer;
}
.lane__list { display: grid; gap: .6rem; min-height: 60px; }
.error { color: #b91c1c; }
</style>