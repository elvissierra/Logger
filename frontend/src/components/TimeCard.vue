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
  const d = new Date(localStr) // local time
  const ms = 15 * 60 * 1000
  const roundedLocal = new Date(Math.round(d.getTime() / ms) * ms)
  return new Date(roundedLocal.getTime() - roundedLocal.getTimezoneOffset() * 60000).toISOString()
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
  const payload = {
    ...local.value,
    // map UI -> API fields
    project_code: local.value.projectCode,
    activity: local.value.activity,
    priority: local.value.priority || 'Normal',
    notes: [local.value.description, local.value.notes].filter(Boolean).join('\n'),
    start_utc: fromLocalInput(local.value.start_local || toLocalInput(local.value.start_utc)),
    end_utc: fromLocalInput(local.value.end_local || toLocalInput(local.value.end_utc)),
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
    :class="{ editing, compact }"
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

    <!-- Compact header: show times + hours + quick edit; optimized for small weekly cells. -->
    <header v-else class="tcard__head tcard__head--compact" @dblclick="editing = true">
      <span class="handle" title="Drag to reorder" aria-label="Drag handle">☰</span>
      <div class="times">
        {{ new Date(card.start_utc).toLocaleTimeString([], {hour:'2-digit', minute:'2-digit'}) }}
        →
        <span v-if="!isRunning && card.end_utc">
          {{ new Date(card.end_utc).toLocaleTimeString([], {hour:'2-digit', minute:'2-digit'}) }}
        </span>
        <span v-else>Now</span>
      </div>
      <div class="hours-lg">{{ fmtH(roundedDurationHours, 2) }} h</div>
      <button class="icon edit-compact" title="Edit" aria-label="Edit" @click.stop="editing = true">✎</button>
    </header>

    <!-- Compact weekly card body (only when not editing) -->
    <section v-if="compact && !editing" class="tcard__body tcard__body--compact"></section>

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
  }
  .tcard:hover { box-shadow: var(--shadow-md, 0 6px 16px rgba(0,0,0,.08)); border-color: color-mix(in srgb, var(--border, #e5e7eb) 70%, var(--primary, #5b8cff) 30%); }
  .tcard.editing { background: var(--panel, #7282c2); }
  .tcard__body { color: var(--text, #374151); min-height: 52px; overflow: hidden; }
  .tcard__body--compact { overflow: hidden; } /* weekly grid variant */
  .tcard__body p { margin: .25rem 0; word-break: break-word; overflow-wrap: anywhere; }
  .tcard .desc,
  .tcard .notes { display: none !important; }
  .tcard__body--compact .desc,
  .tcard__body--compact .notes { display: none; }
  .tcard__head { display: grid; grid-template-columns: auto 1fr auto; align-items: center; gap: .6rem; }
  .handle { cursor: grab; user-select: none; font-size: 1rem; line-height: 1; opacity: .7; }
  .tcard__title { display: flex; align-items: center; gap: .5rem; flex-wrap: wrap; }
  .title { font-weight: 700; letter-spacing: .2px; }
  .chip { font-size: .75rem; padding: .15rem .45rem; border-radius: 999px; background: color-mix(in srgb, var(--primary, #5b8cff) 18%, transparent); color: var(--text, #111827); border: 1px solid var(--border, #e5e7eb); }
  .tcard__title { gap: .45rem; }
  .tcard__title .title { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .hours { font-weight: 600; opacity: .9; }
  .tcard.editing { overflow: visible; }
  /* color-only priority dot */
  .prio-dot { width: 10px; height: 10px; border-radius: 999px; display: inline-block; border: 1px solid var(--border, #e5e7eb); }
  .prio-dot.p-low { background: #93c5fd; border-color: #93c5fd; }
  .prio-dot.p-normal { background: #a5b4fc; border-color: #a5b4fc; }
  .prio-dot.p-high { background: #fdba74; border-color: #fdba74; }
  .prio-dot.p-critical { background: #fca5a5; border-color: #fca5a5; }
  
  /* description clamp */
  .desc.clamped { display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
  .link.more { background: transparent; border: none; color: var(--primary, #5b8cff); padding: 0; cursor: pointer; }
  
  /* footer actions */
  .tcard__foot { display: flex; justify-content: flex-end; gap: .35rem; margin-top: 0; align-self: end;}
  .prio { font-size: .75rem; padding: .15rem .45rem; border-radius: 999px; border: 1px solid var(--border, #e5e7eb); }
  .prio.p-low { background: #eef6ff; color: #1e3a8a; }
  .prio.p-normal { background: #eef2ff; color: #3730a3; }
  .prio.p-high { background: #fff7ed; color: #9a3412; border-color: #fed7aa; }
  .prio.p-critical { background: #fef2f2; color: #991b1b; border-color: #fecaca; }
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
  /* --- Compact variant for weekly grid --- */
  .tcard.compact {
    padding: .4rem .55rem;
    min-height: 72px;
    grid-template-rows: auto;
    align-content: center;
  }
  .tcard__head--compact {
    display: grid;
    grid-template-columns: auto 1fr auto auto; /* handle | times | hours | edit */
    align-items: center;
    gap: .3rem;
  }
  .tcard__head--compact .times {
    font-size: .86rem;
    color: #111827;
    font-weight: 650;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    line-height: 1.1;
  }
  :global([data-theme="dark"]) .tcard__head--compact .times {
    color: #e5f3f0;
  }
  .tcard__head--compact .edit-compact { border-radius: 8px; padding: .2rem .4rem; }
  .hours-lg {
    font-weight: 700;
    font-size: .86rem;
    padding: .08rem .4rem;
    border-radius: 999px;
    background: rgba(47, 143, 131, 0.08);
  }
  .tcard.compact .handle,
  .tcard.compact .tcard__title,
  .tcard.compact .meta,
  .tcard__body--compact .desc,
  .tcard__body--compact .notes { display: none !important; }
  .tcard.compact .tcard__foot { display: none; }
  
  .mini-details { border-top: 1px dashed var(--border); padding-top: .35rem; }
  .mini-details summary { cursor: pointer; color: var(--primary); list-style: none; }
  .mini-details summary::-webkit-details-marker { display: none; }
  
  /* legacy: hide any old text priority pill if present */
  .tcard .prio { display: none !important; }
  
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
  
  
</style>