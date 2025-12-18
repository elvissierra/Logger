<script setup>
import { computed, ref, watch, toRefs } from 'vue'
import draggable from 'vuedraggable'
import TimeCard from './TimeCard.vue'
import { startOfWeek, isSameDay } from '../lib/time'

const props = defineProps({
  layoutMode: { type: String, required: true },
  currentWeekStart: { type: Date, required: true },
  headerDays: { type: Array, required: true },
  swimlanes: { type: Array, required: true },

  runningId: { required: true },
  nowTick: { required: true },

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
  onCellChange: { type: Function, required: true },
  onReorderCell: { type: Function, required: true },
})

const {
  layoutMode,
  currentWeekStart,
  headerDays,
  swimlanes,
  runningId,
  nowTick,
  laneMetaDraft,
} = toRefs(props)

// Keep your existing template working (it references PRIORITIES)
const PRIORITIES = computed(() => props.priorities || [])

function currentUserId () {
  return localStorage.getItem('logger.userId') || null
}

// Today focus
const todayHeader = computed(() =>
  (headerDays.value || []).find(d => d?.date && isSameDay(d.date, new Date()))
)
const todayKey = computed(() => todayHeader.value?.key || null)
const todayLabel = computed(() => todayHeader.value?.label || '')

const showFocus = computed(() => {
  if (!todayKey.value) return false
  return isSameDay(currentWeekStart.value, startOfWeek(new Date()))
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

// Build “today lanes”
const todayLanes = computed(() => {
  if (!todayKey.value) return []
  return (swimlanes.value || [])
    .filter(lane => props.laneVisibleOnDayByProjects(lane.key, todayKey.value))
    .map(lane => ({
      lane,
      col: lane.columns.find(c => c.dayKey === todayKey.value) || { dayKey: todayKey.value, cards: [] },
    }))
})
</script>

<template>

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
    </template>

<style scoped>
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
  background: #ecfdf5;
  color: #065f46;
  border-color: #bbf7d0;
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


</style>