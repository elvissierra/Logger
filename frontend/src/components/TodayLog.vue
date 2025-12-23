<script setup>
import { computed, ref, watch, toRefs } from 'vue'
import TimeCard from './TimeCard.vue'
import { startOfWeek, isSameDay, dateKey, pad } from '../lib/time'

const props = defineProps({
  layoutMode: { type: String, required: true },
  currentWeekStart: { type: Date, required: true },
  headerDays: { type: Array, required: true },
  swimlanes: { type: Array, required: true },

  runningId: { required: true },
  nowTick: { required: true },
  incrementMinutes: { type: Number, default: 15 },

  fmtH: { type: Function, required: true },
  colHours: { type: Function, required: true },

  getLaneMeta: { type: Function, required: true },
  laneVisibleOnDayByProjects: { type: Function, required: true },
  isLaneRunning: { type: Function, required: true },

  priorities: { type: Array, required: true },
  laneMetaDraft: { required: true },
  isEditingLaneMeta: { type: Function, required: true },
  editLaneMeta: { type: Function, required: true },
  saveLaneMeta: { type: Function, required: true },
  cancelLaneMetaEdit: { type: Function, required: true },

  startLaneTimer: { type: Function, required: true },
  startTimer: { type: Function, required: true },
  stopTimer: { type: Function, required: true },
  addCard: { type: Function, required: true },
  saveCard: { type: Function, required: true },
  deleteCard: { type: Function, required: true },

  // Backward-compat (parent may still pass these; we don't use drag/drop in Today)
  onCellChange: { type: Function, required: false },
  onReorderCell: { type: Function, required: false },
})

const { currentWeekStart, headerDays, swimlanes, runningId, nowTick, laneMetaDraft } = toRefs(props)

const PRIORITIES = computed(() => props.priorities || [])

function currentUserId () {
  return localStorage.getItem('logger.userId') || null
}

// Today focus
const todayHeader = computed(() =>
  (headerDays.value || []).find(d => d?.date && isSameDay(d.date, new Date()))
)
const todayKey = computed(() => todayHeader.value?.key || dateKey(new Date()))
const todayLabel = computed(() => todayHeader.value?.label || '')

const showFocus = computed(() => {
  return props.layoutMode === 'grid' && isSameDay(currentWeekStart.value, startOfWeek(new Date()))
})

// Daily plan persistence (local)
const dailyPlan = ref('')
function planKey (dayKey) {
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

function sortMostRecentFirst(cards) {
  return (cards || []).slice().sort((a, b) => {
    const at = a?.start_utc ? new Date(a.start_utc).getTime() : 0
    const bt = b?.start_utc ? new Date(b.start_utc).getTime() : 0
    return bt - at
  })
}

function roundToQuarterHours(h) {
  return Math.round((Number(h) || 0) / 0.25) * 0.25
}

function cardHours(card) {
  try {
    if (!card?.start_utc) return 0
    const s = new Date(card.start_utc).getTime()
    const isRunning = props.runningId && String(card.id) === String(props.runningId)
    const e = isRunning
      ? (Number(props.nowTick) || Date.now())
      : (card.end_utc ? new Date(card.end_utc).getTime() : s)
    return roundToQuarterHours(Math.max(0, (e - s) / 3600000))
  } catch {
    return 0
  }
}

function laneTodayHours(cards) {
  return (cards || []).reduce((sum, c) => sum + cardHours(c), 0)
}

const todayLanes = computed(() => {
  const dayK = todayKey.value
  if (!dayK) return []

  const out = []
  for (const lane of (swimlanes.value || [])) {
    if (!props.laneVisibleOnDayByProjects(lane.key, dayK)) continue

    const col = lane.columns.find(c => c.dayKey === dayK) || { dayKey: dayK, cards: [] }
    const sorted = sortMostRecentFirst(col.cards)
    const running = props.isLaneRunning(lane)

    // Show lanes that have something today OR are currently running.
    if (!sorted.length && !running) continue

    const meta = props.getLaneMeta(lane.key) || {}

    out.push({
      lane,
      col,
      sorted,
      primary: sorted[0] || null,
      older: sorted.slice(1),
      running,
      meta,
      todayHours: laneTodayHours(sorted),
    })
  }

  // Prefer running lane first.
  out.sort((a, b) => Number(b.running) - Number(a.running))
  return out
})

function fmtTodayLabel() {
  const d = new Date()
  const mm = d.toLocaleDateString(undefined, { month: 'short' })
  return `${mm} ${pad(d.getDate())}`
}
</script>

<template>
  <section v-if="showFocus" class="focus focus--inboard">
    <header class="focus__header">
      <strong>Today — {{ todayLabel }}</strong>
      <span class="focus__hours">{{ fmtH(colHours(todayKey), 2) }} h</span>
    </header>

    <div class="focus__layout">
      <aside class="focus__plan">
        <div class="focus__planhead">
          <label class="focus__label">Today’s plan</label>
          <span class="focus__date">{{ fmtTodayLabel() }}</span>
        </div>
        <textarea
          v-model="dailyPlan"
          rows="8"
          class="focus__textarea"
          placeholder='e.g., "this is what I plan to work on today"'
        ></textarea>
      </aside>

      <div class="focus__col">
        <section
          v-for="x in todayLanes"
          :key="x.lane.key"
          class="todayLane"
          :class="'prio-' + String((x.meta.priority || 'Normal')).toLowerCase()"
        >
          <header class="todayLane__head">
            <div class="todayLane__left">
              <strong class="todayLane__title">{{ x.lane.title }}</strong>
              <span
                v-if="x.meta.priority"
                class="badge"
                :class="'p-' + String((x.meta.priority || 'Normal')).toLowerCase()"
              >
                {{ x.meta.priority }}
              </span>
              <span v-if="x.running" class="badge badge--running">Running</span>
            </div>

            <div class="todayLane__actions">
              <button
                class="mini icon"
                @click="x.running ? stopTimer() : startLaneTimer(x.lane)"
                :title="x.running ? 'Stop timer' : 'Start timer'"
              >
                {{ x.running ? '■' : '▶︎' }}
              </button>
              <button class="mini icon" @click="editLaneMeta(x.lane)" title="Project details">⋯</button>
              <button class="mini icon" @click="addCard(x.lane, x.col)" title="Add entry">＋</button>
            </div>
          </header>

          <div class="todayLane__details" v-if="!isEditingLaneMeta(x.lane.key)">
            <div class="todayLane__detailLeft">
              <span class="pill">{{ fmtH(x.todayHours, 2) }} h</span>
              <span class="pill">{{ x.sorted.length }} entr<span v-if="x.sorted.length !== 1">ies</span></span>

              <span class="todayLane__desc" v-if="x.meta.description" :title="x.meta.description">
                {{ x.meta.description }}
              </span>
              <span class="todayLane__desc todayLane__desc--empty" v-else>
                No project notes yet
              </span>
            </div>
          </div>

          <div v-if="isEditingLaneMeta(x.lane.key)" class="lane-meta-editor lane-meta-editor--focus">
            <label class="lane-meta-editor__field">
              <span>Priority</span>
              <select v-model="laneMetaDraft.priority">
                <option v-for="p in PRIORITIES" :key="p" :value="p">{{ p }}</option>
              </select>
            </label>
            <label class="lane-meta-editor__field">
              <span>Project notes</span>
              <textarea
                v-model="laneMetaDraft.description"
                rows="2"
                placeholder="Project-level context, blockers, next steps"
              ></textarea>
            </label>
            <div class="lane-meta-editor__actions">
              <button type="button" class="mini" @click="saveLaneMeta(x.lane)">Save</button>
              <button type="button" class="mini" @click="cancelLaneMetaEdit">Cancel</button>
            </div>
          </div>

          <div v-if="x.primary" class="todayLane__primary">
            <TimeCard
              :card="x.primary"
              :open-on-mount="x.primary.__new === true"
              :running-id="runningId"
              :now-tick="nowTick"
              :increment-minutes="incrementMinutes"
              :compact="false"
              @start="startTimer"
              @stop="stopTimer"
              @save="saveCard"
              @delete="c => deleteCard(x.lane, x.col, c)"
            />
          </div>

          <details v-if="x.older.length" class="todayLane__older">
            <summary>
              Earlier entries ({{ x.older.length }})
              <span class="muted">• {{ fmtH(laneTodayHours(x.older), 2) }} h</span>
            </summary>
            <div class="todayLane__olderList">
              <TimeCard
                v-for="c in x.older"
                :key="c.id"
                :card="c"
                :open-on-mount="c.__new === true"
                :running-id="runningId"
                :now-tick="nowTick"
                :increment-minutes="incrementMinutes"
                :compact="false"
                @start="startTimer"
                @stop="stopTimer"
                @save="saveCard"
                @delete="cc => deleteCard(x.lane, x.col, cc)"
              />
            </div>
          </details>
        </section>

        <div v-if="!todayLanes.length" class="today__empty">
          <div class="today__emptyTitle">No entries for today yet.</div>
          <div class="today__emptyHint">Use the plus button on a project to add your first entry for today.</div>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
/* (Styles identical to the earlier patch concept; kept concise and local to TodayLog) */
.focus { width: 100%; margin: 12px 0 16px; background: var(--panel); border: 1px solid var(--border); border-radius: var(--radius); box-shadow: var(--shadow-sm); }
.focus__header { display: flex; justify-content: space-between; align-items: baseline; padding: 12px 14px; border-bottom: 1px solid var(--border); }
.focus__hours { color: var(--muted); font-weight: 700; }
.focus__layout { display: grid; align-items: start; grid-template-columns: 340px 1fr; gap: 16px; padding: 12px; }
@media (max-width: 1100px) { .focus__layout { grid-template-columns: 1fr; } }
.focus__plan { display: grid; gap: 8px; position: sticky; top: 0; align-self: start; }
.focus__planhead { display: flex; justify-content: space-between; align-items: baseline; }
.focus__label { font-weight: 700; color: var(--muted); }
.focus__date { font-size: 0.8rem; color: var(--muted); }
.focus__textarea { width: 100%; min-height: 180px; resize: vertical; padding: 0.6rem 0.7rem; border: 1px solid var(--border); border-radius: 10px; background: var(--panel-2); color: var(--text); }

.focus__col { display: grid; gap: 12px; }

.todayLane {
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 12px;
  overflow: hidden;
  box-shadow: var(--shadow-md, 0 6px 16px rgba(0,0,0,.08));
  transition: box-shadow .15s ease, border-color .15s ease;
}
.todayLane:hover {
  box-shadow: var(--shadow-lg, 0 10px 28px rgba(0,0,0,.12));
  border-color: color-mix(in srgb, var(--border) 60%, var(--primary) 40%);
}
.todayLane__head { display: flex; justify-content: space-between; align-items: center; padding: 8px 10px; border-bottom: 1px solid var(--border); }
.todayLane__left { display: flex; align-items: center; gap: 8px; min-width: 0; }
.todayLane__title { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.todayLane__actions { display: flex; gap: 6px; }

.todayLane__details { padding: 8px 10px; border-bottom: 1px solid color-mix(in srgb, var(--border) 70%, transparent); background: color-mix(in srgb, var(--panel-2) 82%, transparent); }
.todayLane__detailLeft { display: flex; align-items: center; gap: 8px; min-width: 0; }
.pill { font-size: 0.78rem; font-weight: 750; padding: 0.14rem 0.55rem; border-radius: 999px; border: 1px solid color-mix(in srgb, var(--border) 80%, transparent); background: color-mix(in srgb, var(--panel) 85%, transparent); white-space: nowrap; }
.todayLane__desc { font-size: 0.82rem; color: var(--text); opacity: 0.92; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 520px; }
.todayLane__desc--empty { color: var(--muted); }

.todayLane__primary { padding: 10px; display: grid; gap: 10px; }
.todayLane__older { margin: 0 10px 10px; border-radius: 12px; border: 1px solid color-mix(in srgb, var(--border) 82%, transparent); background: color-mix(in srgb, var(--panel) 92%, transparent); padding: 6px 8px; }
.todayLane__older summary { cursor: pointer; list-style: none; font-weight: 750; font-size: 0.84rem; }
.todayLane__older summary::-webkit-details-marker { display: none; }
.todayLane__older .muted { font-weight: 650; color: var(--muted); }
.todayLane__olderList { display: grid; gap: 10px; margin-top: 10px; }

.badge { font-size: 0.72rem; padding: 0.1rem 0.45rem; border-radius: 999px; border: 1px solid var(--border); }
.badge.p-low { background: #eef6ff; color: #1e3a8a; }
.badge.p-normal { background: #ecfdf5; color: #065f46; border-color: #bbf7d0; }
.badge.p-high { background: #fff7ed; color: #9a3412; border-color: #fed7aa; }
.badge.p-critical { background: #fef2f2; color: #991b1b; border-color: #fecaca; }
.badge--running { background: color-mix(in srgb, var(--primary) 14%, transparent); }

.lane-meta-editor { margin: 8px 10px 10px; padding: 8px; border-radius: 12px; background: color-mix(in srgb, var(--panel-2) 85%, transparent); border: 1px solid color-mix(in srgb, var(--border) 85%, transparent); display: grid; gap: 6px; }
.lane-meta-editor__field { display: grid; gap: 4px; font-size: 0.78rem; color: var(--muted); }
.lane-meta-editor__field select, .lane-meta-editor__field textarea { background: var(--panel); border: 1px solid var(--border); border-radius: 10px; padding: 0.35rem 0.55rem; color: var(--text); font-size: 0.82rem; }
.lane-meta-editor__actions { display: flex; justify-content: flex-end; gap: 6px; }

.today__empty { padding: 14px; border-radius: 14px; border: 1px dashed color-mix(in srgb, var(--border) 80%, transparent); color: var(--muted); }
.today__emptyTitle { font-weight: 750; color: var(--text); margin-bottom: 4px; }
</style>