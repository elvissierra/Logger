<script setup>
/**
 * Knowledge Drop — TimeCard.vue (single time entry)
 *
 * Purpose
 * - Renders one time entry. Two modes: full card (Focus area) and compact card (Weekly/Simple lists).
 * - Handles in-place editing with datetime-local fields rounded to 15‑minute increments.
 *
 * How it collaborates
 * - Receives `runningId` & `nowTick` from the parent to compute live durations without its own timers.
 * - Emits `save`, `delete`, `start`, `stop` so the parent can persist and manage global running state.
 * - Uses a defensive clone of props for editing so we don’t mutate parent state directly.
 *
 * Why necessary
 * - Centralizes entry UX (display + edit) so both layouts render identical semantics with different density.
 *
 * Notes
 * - Duration is derived from start/end or from now when running; parent decides what “running” means.
 * - We intentionally hide description/notes in compact mode to keep weekly cells small.
 */

import { ref, watch, computed, onMounted, onUnmounted, nextTick } from 'vue'

function roundToQuarterHours(h) {
  return Math.round((Number(h) || 0) / 0.25) * 0.25
}

const clone = (obj) => {
  try {
    if (typeof structuredClone === 'function') return structuredClone(obj)
  } catch (_) { /* fall through */ }
  try { return JSON.parse(JSON.stringify(obj)) } catch { return obj ? { ...obj } : obj }
}

const props = defineProps({
  card: { type: Object, required: true },
  openOnMount: { type: Boolean, default: false },
  runningId: { type: String, default: null },
  nowTick: { type: Number, default: 0 },
  compact: { type: Boolean, default: false },
  heightPx: { type: Number, default: null }
})
const emit = defineEmits(['save', 'delete', 'start', 'stop'])
const isRunning = computed(() => props.runningId && props.card.id === props.runningId)
const showFullDesc = ref(false)
const isClampedCandidate = computed(() => (props.card.description || '').length > 120)

const editing = ref(false)
const local = ref(clone(props.card))
if (!('priority' in local.value)) local.value.priority = 'Normal'
watch(() => props.card, (v) => { local.value = clone(v) }, { deep: true })

// When entering edit mode, seed datetime-local fields from the card
watch(editing, (on) => {
  if (on) {
    local.value.start_local = toLocalInput(props.card.start_utc)
    local.value.end_local = toLocalInput(props.card.end_utc)
  }
})

// Keep local datetime fields in sync if the card changes while not editing
watch(() => props.card, (v) => {
  if (!editing.value) {
    local.value.start_local = toLocalInput(v.start_utc)
    local.value.end_local = toLocalInput(v.end_utc)
  }
}, { deep: true })

// Auto-open editor for new cards / when requested
onMounted(() => {
  const tmp = props.card && String(props.card.id || '').startsWith('tmp_')
  if (props.openOnMount || tmp) {
    editing.value = true
    local.value.start_local = local.value.start_local || toLocalInput(local.value.start_utc)
    local.value.end_local   = local.value.end_local   || toLocalInput(local.value.end_utc)
  }
  if (!local.value.priority) local.value.priority = 'Normal'
})
function onKey(e){
  if (!editing.value) return
  if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase()==='s'){ e.preventDefault(); onSave() }
  else if (e.key==='Escape'){ e.preventDefault(); editing.value=false }
}
function fmtH(n, d = 1) {
  const x = Number(n)
  return Number.isFinite(x) ? x.toFixed(d) : (0).toFixed(d)
}

onMounted(()=>window.addEventListener('keydown', onKey))
onUnmounted(()=>window.removeEventListener('keydown', onKey))

// Convert ISO (UTC) -> value for <input type="datetime-local"> in the user’s local timezone (no seconds);
// Important: subtract timezone offset so the local field shows the correct wall time.
function toLocalInput(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  d.setMinutes(d.getMinutes() - d.getTimezoneOffset())
  return d.toISOString().slice(0, 16) // YYYY-MM-DDTHH:mm
}
// Convert local datetime string -> ISO (UTC), rounding to nearest 15 minutes to match the app’s granularity.
function fromLocalInput(localStr) {
  if (!localStr) return ''
  const d = new Date(localStr) // interpreted as local time
  const ms = 15 * 60 * 1000
  const roundedLocal = new Date(Math.round(d.getTime() / ms) * ms)
  // Browser already converted local time to the right UTC instant; just emit ISO
  return roundedLocal.toISOString()
}

// Live duration: when running, use nowTick; otherwise use end_utc (or 0 if missing).
const durationHours = computed(() => {
  if (!props.card.start_utc) return 0
  const s = new Date(props.card.start_utc).getTime()
  const e = isRunning.value ? (props.nowTick || Date.now()) : (props.card.end_utc ? new Date(props.card.end_utc).getTime() : s)
  return Math.max(0, (e - s) / 3600000)
})
const roundedDurationHours = computed(() => roundToQuarterHours(durationHours.value))

// Compact editor: start with basic fields; allow expanding to advanced
const showAdvanced = ref(false)
const advFirst = ref(null)
watch(editing, (on) => { if (on) showAdvanced.value = false })
watch(showAdvanced, async (open) => {
  if (open) await nextTick().then(() => { advFirst.value?.focus?.() })
})

function onSave() {
  const title = (local.value.jobTitle || '').trim()
  if (!title) {
    window.alert('Please enter Title')
    return
  }
  const startIso = fromLocalInput(local.value.start_local || toLocalInput(local.value.start_utc))
  const endIso = local.value.end_local
    ? fromLocalInput(local.value.end_local)
    : (local.value.end_utc ? fromLocalInput(toLocalInput(local.value.end_utc)) : null)

  const payload = {
    ...local.value,
    // map UI -> API fields
    project_code: local.value.projectCode,
    activity: local.value.activity,
    job_title: local.value.jobTitle || null,
    priority: local.value.priority || 'Normal',
    notes: [local.value.description, local.value.notes].filter(Boolean).join('\n'),
    start_utc: startIso,
    end_utc: endIso,
  }
  emit('save', payload)
  editing.value = false
}
function onDelete() { emit('delete', props.card) }
function onStart(){ emit('start', props.card) }
function onStop(){ emit('stop', props.card) }
</script>

<template>
  <article
    class="tcard"
    :class="[{ editing, compact }, 'prio-' + String(card.priority || 'Normal').toLowerCase()]"
    :style="(compact && !editing)
        ? { minHeight: ((heightPx || 56)) + 'px' }
        : {}"
  >
    <!-- Full header (focus cards) -->
    <header v-if="!compact" class="tcard__head">
      <span class="handle" title="Drag to reorder" aria-label="Drag handle">☰</span>
      <div class="tcard__title">
        <span class="prio-dot" :class="('p-' + (card.priority || 'Normal').toLowerCase())" :title="card.priority || 'Normal'"></span>
        <strong class="title" :title="card.jobTitle || card.projectCode || 'Untitled'">
          {{ card.jobTitle || card.projectCode || 'Untitled' }}
        </strong>
        <span class="chip" v-if="card.activity">{{ card.activity }}</span>
      </div>
      <div class="hours" v-if="roundedDurationHours > 0">{{ fmtH(roundedDurationHours, 2) }} h</div>
    </header>

    <!-- Compact header: show times + optional label; optimized for small weekly cells. -->
    <header v-else class="tcard__head tcard__head--compact" @dblclick="editing = true">
      <span class="handle" title="Drag to reorder" aria-label="Drag handle">☰</span>
      <div class="times">
        <!-- Project / lane label first (top line) -->
        <div
          v-if="card.jobTitle || card.projectCode || card.activity"
          class="times__label"
          :title="(card.jobTitle || card.projectCode || 'Untitled') + (card.activity ? ' — ' + card.activity : '')"
        >
          <span class="times__label-main">
            {{ card.jobTitle || card.projectCode || 'Untitled' }}
          </span>
          <span v-if="card.activity" class="times__label-sep"> • </span>
          <span v-if="card.activity" class="times__label-activity">
            {{ card.activity }}
          </span>
        </div>

        <!-- Time range second (stacked start/end for strict separation) -->
        <div class="times__range">
          <div class="times__row times__row--start">
            {{ new Date(card.start_utc).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) }}
          </div>
          <div class="times__row times__row--end">
            <span v-if="!isRunning && card.end_utc">
              {{ new Date(card.end_utc).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) }}
            </span>
            <span v-else>Now</span>
          </div>
        </div>
      </div>
      <button
        class="icon edit-compact"
        title="Edit"
        aria-label="Edit"
        @click.stop="editing = true"
      >
        ✎
      </button>
    </header>

    <!-- Compact weekly card body (only when not editing) -->
    <section v-if="compact && !editing" class="tcard__body tcard__body--compact">
      <div class="mini-meta-row">
        <span
          v-if="card.priority && card.priority !== 'Normal'"
          class="mini-meta__pri"
          :class="'p-' + (card.priority || 'Normal').toLowerCase()"
        >
          {{ card.priority }}
        </span>
        <span class="hours-lg">
          {{ fmtH(roundedDurationHours, 2) }} h
        </span>
      </div>
    </section>

    <!-- Full card body (focus area) shown when not editing) -->
    <section v-else-if="!compact && !editing" class="tcard__body" @dblclick="editing = true">
      <div class="meta" v-if="card.start_utc && card.end_utc">
        <span class="time">
          {{ new Date(card.start_utc).toLocaleTimeString([], {hour:'2-digit', minute:'2-digit'}) }} →
          {{ new Date(card.end_utc).toLocaleTimeString([], {hour:'2-digit', minute:'2-digit'}) }}
        </span>
        <span class="sep">•</span>
        <span class="hours">{{ fmtH(roundedDurationHours, 2) }} h</span>
      </div>
    </section>

    <!-- Editor (appears for both compact and full when editing=true). step=900 enforces 15‑minute increments. -->
    <section v-else class="tcard__edit" :class="{ 'tcard__edit--compact': compact }">
      <!-- BASIC FIELDS -->
      <div class="grid grid--basic">
        <label>Job Title
          <input v-model="local.jobTitle" placeholder="Bridge Inspection" />
        </label>
        <label>Project Code
          <input v-model="local.projectCode" placeholder="PJ-001" />
        </label>
        <label>Activity
          <input v-model="local.activity" placeholder="Paperwork / Field Work / Travel" />
        </label>
        <div class="row">
          <label>Start
            <input type="datetime-local" step="900" v-model="local.start_local" />
          </label>
          <label>End
            <input type="datetime-local" step="900" v-model="local.end_local" />
          </label>
        </div>
      </div>

      <!-- TOGGLE -->
      <button
        type="button"
        class="link more toggle-adv"
        @click="showAdvanced = !showAdvanced"
        :aria-expanded="String(showAdvanced)"
      >
        {{ showAdvanced ? 'Hide advanced ▲' : 'More fields ▸' }}
      </button>
      <!-- ADVANCED (dropdown-style) -->
      <div v-show="showAdvanced" class="grid grid--advanced">
        <label>Urgency
          <select v-model="local.priority">
            <option v-for="p in ['Low','Normal','High','Critical']" :key="p" :value="p">{{ p }}</option>
          </select>
        </label>
        <label>Description
          <textarea v-model="local.description" rows="2" placeholder="What you worked on"></textarea>
        </label>
        <label>Notes
          <textarea v-model="local.notes" rows="2" placeholder="Optional notes"></textarea>
        </label>
      </div>

      <div class="actions">
        <button type="button" class="primary" @click="onSave">Save</button>
        <span class="hint">⌘/Ctrl+S</span>
        <button type="button" class="secondary" @click="editing=false">Cancel</button>
        <button type="button" class="danger" @click="onDelete">Delete</button>
      </div>
    </section>
    <footer v-if="!compact" class="tcard__foot">
      <div class="spacer"></div>
      <div class="actions__icons">
        <button class="icon" :title="isRunning ? 'Stop' : 'Start'" :aria-label="isRunning ? 'Stop' : 'Start'" @click="isRunning ? onStop() : onStart()">
          {{ isRunning ? '■' : '▶︎' }}
        </button>
        <button class="icon" title="Edit" aria-label="Edit" @click="editing = !editing">✎</button>
      </div>
    </footer>
  </article>
</template>

<style scoped>
  /* Knowledge Drop — Card styles: full vs compact, hover states, and small in-card controls */
  .tcard {
    display: grid;
    grid-template-rows: auto 1fr auto; /* header | body grows | footer at bottom */
    grid-auto-rows: min-content;
    gap: .55rem;
    background: var(--card, #ffffff);
    border: 1px solid var(--border, #e5e7eb);
    border-radius: var(--radius, 12px);
    padding: .75rem .9rem;
    box-shadow: var(--shadow-sm, 0 1px 2px rgba(0,0,0,.06));
    transition: box-shadow .15s ease, transform .08s ease, border-color .2s ease, background .2s ease;
    overflow: hidden;
    min-height: 112px;
    color: var(--text, #111827);
    position: relative;
  }
  .tcard:hover { box-shadow: var(--shadow-md, 0 6px 16px rgba(0,0,0,.08)); border-color: color-mix(in srgb, var(--border, #e5e7eb) 70%, var(--primary, #5b8cff) 30%); }
  
  .tcard__body { color: var(--text, #374151); min-height: 52px; overflow: hidden; }
/* Folder tab on compact cards – wide, rounded strip */
.tcard.compact::before {
  content: '';
  position: absolute;
  top: -2px;
  left: 10px;
  width: 78%;
  height: 13px;
  border-radius: 10px 10px 0 0;
  background: color-mix(in srgb, var(--primary, #5b8cff) 22%, transparent);
  box-shadow: 0 1px 0 rgba(0, 0, 0, 0.04);
  opacity: 0.96;
}

/* Priority colors for the tab */
.tcard.compact.prio-low::before {
  background: #93c5fd;
}
.tcard.compact.prio-normal::before {
  background: #a5b4fc;
}
.tcard.compact.prio-high::before {
  background: #fdba74;
}
.tcard.compact.prio-critical::before {
  background: #fca5a5;
}

/* Expand compact cards on hover */
.tcard.compact:hover {
  max-height: 168px;
  transform: translateY(-2px);
  box-shadow: var(--shadow-md, 0 8px 24px rgba(0,0,0,.08));
}

/* Compact body is hidden until hover */
.tcard__body--compact {
  overflow: hidden;
  max-height: 0;
  opacity: 0;
  transition: max-height .15s ease, opacity .15s ease;
  display: flex;
  flex-direction: column;
  justify-content: flex-end;
  gap: 4px;
}

.mini-meta-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 4px;
}

.tcard.compact:hover .tcard__body--compact {
  max-height: 80px;
  opacity: 1;
}
  .tcard__body p { margin: .25rem 0; word-break: break-word; overflow-wrap: anywhere; }
  
  .tcard__head { display: grid; grid-template-columns: auto 1fr auto; align-items: center; gap: .6rem; }
  .handle { cursor: grab; user-select: none; font-size: 1rem; line-height: 1; opacity: .7; }
  .tcard__title { display: flex; align-items: center; gap: .5rem; flex-wrap: wrap; }
  .title { font-weight: 700; letter-spacing: .2px; }
  .chip { font-size: .75rem; padding: .15rem .45rem; border-radius: 999px; background: color-mix(in srgb, var(--primary, #5b8cff) 18%, transparent); color: var(--text, #111827); border: 1px solid var(--border, #e5e7eb); }
  .tcard__title { gap: .45rem; }
  .tcard__title .title { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .hours { font-weight: 600; opacity: .9; }
  .tcard.editing { 
    background: var(--panel, #7282c2);
    overflow: visible; 
  }
  /* color-only priority dot */
  .prio-dot { width: 10px; height: 10px; border-radius: 999px; display: inline-block; border: 1px solid var(--border, #e5e7eb); }
  .prio-dot.p-low { background: #93c5fd; border-color: #93c5fd; }
  .prio-dot.p-normal { background: #a5b4fc; border-color: #a5b4fc; }
  .prio-dot.p-high { background: #fdba74; border-color: #fdba74; }
  .prio-dot.p-critical { background: #fca5a5; border-color: #fca5a5; }
  
  /* description clamp */
  .link.more { background: transparent; border: none; color: var(--primary, #5b8cff); padding: 0; cursor: pointer; }
  
  /* footer actions */
  .tcard__foot { display: flex; justify-content: flex-end; gap: .35rem; margin-top: 0; align-self: end;}
  
  .icon { border: 1px solid var(--border, #e5e7eb); border-radius: 8px; background: var(--panel-2, #f3f4f6); cursor: pointer; padding: .25rem .45rem; line-height: 1; }
  .icon:hover { background: #e9eef7; }
  .hint{ align-self:center; color:var(--muted); font-size:.85rem; margin-left:.25rem; }
  
  .tcard__edit .grid { display: grid; gap: .35rem; }
  .tcard__edit label { display: grid; gap: .2rem; }
  .tcard__edit .row { display: grid; grid-template-columns: minmax(0,1fr) minmax(0,1fr); gap: .35rem; }
  
  input, textarea, button { font: inherit; color: var(--text, #111827); }
  
  input, textarea {
    width: 100%;
    max-width: 100%;
    box-sizing: border-box;
    padding: .4rem .5rem;
    border: 1px solid var(--border, #d1d5db);
    border-radius: 8px;
    background: var(--panel, #ffffff);
  }
  @media (max-width: 520px) {
    .tcard__edit .row { grid-template-columns: 1fr; }
  }
  select { width: 100%; max-width: 100%; box-sizing: border-box; }
  
  input[type="datetime-local"] { line-height: 1.2; }
  
  input[type="datetime-local"] {
    font-size: .9rem;
    padding: .32rem .45rem;
    white-space: nowrap;     /* keep on one line */
    overflow: hidden;        /* hide overflow */
    text-overflow: ellipsis; /* show … when too long */
  }
  /* WebKit/Blink: compact the inner datetime editor pieces */
  input[type="datetime-local"]::-webkit-datetime-edit { padding: 0; }
  input[type="datetime-local"]::-webkit-datetime-edit-fields-wrapper { display: flex; }
  input[type="datetime-local"]::-webkit-datetime-edit-year-field,
  input[type="datetime-local"]::-webkit-datetime-edit-month-field,
  input[type="datetime-local"]::-webkit-datetime-edit-day-field,
  input[type="datetime-local"]::-webkit-datetime-edit-hour-field,
  input[type="datetime-local"]::-webkit-datetime-edit-minute-field,
  input[type="datetime-local"]::-webkit-datetime-edit-ampm-field {
    padding: 0 .15em;
  }
  input[type="datetime-local"]::-webkit-calendar-picker-indicator { padding: 0 .2rem; }
  input, textarea, select { font-variant-numeric: tabular-nums; }
  .actions { display: flex; gap: .4rem; justify-content: flex-end; }
  button {
    padding: .45rem .7rem; border: 1px solid var(--border, #d1d5db); border-radius: 8px; background: var(--panel-2, #f9fafb);
    cursor: pointer; transition: background .15s ease, border-color .15s ease, transform .06s ease;
  }
  button:hover { background: #f0f2f6; }
  button:active { transform: translateY(1px); }
  button.primary { background: linear-gradient(180deg, var(--primary, #5b8cff), var(--primary-600, #3e6dff)); border-color: color-mix(in srgb, var(--border, #d1d5db) 40%, var(--primary, #5b8cff) 60%); color: #fff; }
  button.danger { border-color: #ef4444; color: #b91c1c; }
  .actions__icons { display: flex; gap: .35rem; }
  
.tcard.compact {
  padding: .8rem .6rem .7rem .6rem;
  min-height: 48px;
  grid-template-rows: auto;
  align-content: flex-start;
  position: relative;
  max-height: 68px;
  overflow: hidden;
  transition:
    max-height .15s ease,
    transform .12s ease,
    box-shadow .12s ease;
}

.tcard.compact.editing {
  max-height: none; /* allow full height while editing */
}

.tcard__head--compact {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto; /* handle | title+times | edit */
  align-items: center;
  gap: .35rem;
}

.tcard__head--compact .times {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.times__range {
  font-size: .84rem;
  font-weight: 600;
  color: var(--text, #111827);
  font-variant-numeric: tabular-nums;
  line-height: 1.1;
  display: flex;
  flex-direction: column;
  gap: 1px;
}

.times__row {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

:global([data-theme="dark"]) .times__range {
  color: #e5f3f0;
}

  .times__label {
    font-size: .75rem;
    color: var(--muted, #6b7280);
    line-height: 1.1;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .times__label-main {
    font-weight: 500;
  }
  .times__label-sep {
    opacity: .65;
    padding: 0 .12rem;
  }
  .times__label-activity {
    color: var(--muted, #6b7280);
  }

.tcard__head--compact .edit-compact {
  border-radius: 8px;
  padding: .2rem .4rem;
  opacity: 0;
  pointer-events: none;
  transition: opacity .12s ease;
}

.tcard.compact:hover .tcard__head--compact .edit-compact {
  opacity: 1;
  pointer-events: auto;
}

.hours-lg {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 3.25rem;
  font-weight: 600;
  font-size: .8rem;
  padding: .12rem .55rem;
  border-radius: 999px;
  background: color-mix(in srgb, var(--primary, #5b8cff) 8%, transparent);
  color: var(--text, #111827);
}

.tcard.compact .hours-lg {
  margin-left: auto;
}

:global([data-theme="dark"]) .hours-lg {
  background: rgba(127, 209, 195, 0.16);
  color: #e5f3f0;
}

.tcard.compact .handle,
.tcard.compact .tcard__title,
.tcard.compact .meta,
.tcard__body--compact .desc,
.tcard__body--compact .notes { display: none !important; }

.tcard.compact .tcard__foot { display: none; }
  
  /* When a compact card is editing, stack Start/End vertically to avoid overflow */
  .tcard.compact.editing .tcard__edit .row { grid-template-columns: 1fr; }
  
  /* Slightly reduce padding while editing (compact) to gain horizontal room */
  .tcard.compact.editing { padding: .6rem .6rem; }
  
  /* Keep datetime inputs within bounds and a bit tighter in compact edit mode */
  .tcard.compact.editing input[type="datetime-local"] {
    width: 100%;
    max-width: 100%;
    font-size: .88rem;
    padding: .3rem .45rem;
  }
  
  .mini-meta {
    display: flex;
    align-items: center;
    gap: 4px;
    margin-top: 2px;
    font-size: .72rem;
    color: var(--muted, #6b7280);
  }
  .mini-meta__pri {
    padding: .05rem .35rem;
    border-radius: 999px;
    border: 1px solid var(--border, #d1d5db);
    font-weight: 600;
  }
  .mini-meta__pri.p-low {
    background: #eef6ff;
    color: #1e3a8a;
    border-color: #bfdbfe;
  }
  .mini-meta__pri.p-normal {
    background: #eef2ff;
    color: #3730a3;
    border-color: #c7d2fe;
  }
  .mini-meta__pri.p-high {
    background: #fff7ed;
    color: #9a3412;
    border-color: #fed7aa;
  }
  .mini-meta__pri.p-critical {
    background: #fef2f2;
    color: #991b1b;
    border-color: #fecaca;
  }
  .mini-meta__notes {
    font-size: .8rem;
  }
</style>