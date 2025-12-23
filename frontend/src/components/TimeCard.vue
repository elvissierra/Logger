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
  tabSide: { type: String, default: 'left' }, // 'left' | 'right'
  collapsed: { type: Boolean, default: false },
  incrementMinutes: { type: Number, default: 15 },
  stackIndex: { type: Number, default: 0 }
})
const emit = defineEmits(['save', 'delete', 'start', 'stop'])
const isRunning = computed(() => props.runningId && String(props.card.id) === String(props.runningId))

const incMins = computed(() => {
  const n = Number(props.incrementMinutes)
  if (!Number.isFinite(n)) return 15
  return Math.min(60, Math.max(1, Math.round(n)))
})
const stepSeconds = computed(() => incMins.value * 60)

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
// Convert local datetime string -> ISO (UTC), rounding to nearest increment to match the app’s granularity.
function fromLocalInput(localStr) {
  if (!localStr) return ''
  const d = new Date(localStr) // interpreted as local time
  const ms = incMins.value * 60 * 1000
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
  let endIsoSafe = endIso
  if (endIsoSafe) {
    const s = new Date(startIso).getTime()
    const e = new Date(endIsoSafe).getTime()
    if (Number.isFinite(s) && Number.isFinite(e) && e < s) {
      // Clamp to at least one increment after start.
      endIsoSafe = new Date(s + (incMins.value * 60 * 1000)).toISOString()
    }
  }

  const payload = {
    ...local.value,
    // map UI -> API fields
    project_code: local.value.projectCode,
    activity: local.value.activity,
    job_title: local.value.jobTitle || null,
    priority: local.value.priority || 'Normal',
    notes: [local.value.description, local.value.notes].filter(Boolean).join('\n'),
    start_utc: startIso,
    end_utc: endIsoSafe,
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
    :class="[
      { editing, compact },
      'prio-' + String(card.priority || 'Normal').toLowerCase()
    ]"
  >
    <!-- Full header (focus cards) -->
    <header v-if="!compact && !editing" class="tcard__head">
      <span class="grip" aria-hidden="true">☰</span>
      <div class="tcard__title">
        <span
          class="prio-dot"
          :class="('p-' + (card.priority || 'Normal').toLowerCase())"
          :title="card.priority || 'Normal'"
        ></span>
        <strong class="title" :title="card.jobTitle || card.projectCode || 'Untitled'">
          {{ card.jobTitle || card.projectCode || 'Untitled' }}
        </strong>
        <span class="chip" v-if="card.activity">{{ card.activity }}</span>
      </div>
      <div class="hours" v-if="roundedDurationHours > 0">{{ fmtH(roundedDurationHours, 2) }} h</div>
    </header>

    <!-- Editor (editing wins in all modes) -->
    <section v-if="editing" class="tcard__edit" :class="{ 'tcard__edit--compact': compact }">
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
            <input type="datetime-local" :step="stepSeconds" v-model="local.start_local" />
          </label>
          <label>End
            <input type="datetime-local" :step="stepSeconds" v-model="local.end_local" />
          </label>
        </div>
      </div>

      <button
        type="button"
        class="link more toggle-adv"
        @click="showAdvanced = !showAdvanced"
        :aria-expanded="String(showAdvanced)"
      >
        {{ showAdvanced ? 'Hide advanced ▲' : 'More fields ▸' }}
      </button>

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

    <!-- Compact (weekly/simple) strict folder card when not editing -->
    <template v-else-if="compact">
      <section
        class="folderCard"
        :class="[
          'folderCard--tab-' + (tabSide === 'right' ? 'right' : 'left'),
          'folderCard--tone-' + (((Number(stackIndex) || 0) % 4) + 1),
          { 'folderCard--collapsed': !!collapsed }
        ]"
        @dblclick="editing = true"
      >
        <!-- Folder tab (visual only) -->
        <div class="folderCard__tab" aria-hidden="true">
          <span class="grip folderCard__grip" aria-hidden="true">≡</span>
        </div>
        <!-- Folder body -->
        <div class="folderCard__body">
          <div class="folderCard__main">
            <div class="folderCard__title" :title="card.jobTitle || 'Untitled'">
              {{ card.jobTitle || 'Untitled' }}
            </div>
            <div v-if="!collapsed && card.activity" class="folderCard__sub" :title="card.activity">
              {{ card.activity }}
            </div>
            <div v-if="!collapsed" class="folderCard__times">
              <div class="folderCard__time">
                {{ card.start_utc ? new Date(card.start_utc).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '--:--' }}
              </div>
              <div class="folderCard__time">
                <span v-if="!isRunning && card.end_utc">
                  {{ new Date(card.end_utc).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) }}
                </span>
                <span v-else>Now</span>
              </div>
            </div>
          </div>
          <!-- Right action rail (stacked) -->
          <div v-if="!collapsed" class="folderCard__rail">
            <button
              class="folderCard__btn"
              :title="isRunning ? 'Stop' : 'Start'"
              :aria-label="isRunning ? 'Stop' : 'Start'"
              @click.stop="isRunning ? onStop() : onStart()"
            >
              {{ isRunning ? '■' : '▶︎' }}
            </button>
            <button
              class="folderCard__btn"
              title="Edit"
              aria-label="Edit"
              @click.stop="editing = true"
            >
              ⋯
            </button>
          </div>
          <!-- Footer pills -->
          <div v-if="!collapsed" class="folderCard__footer">
            <span class="folderCard__pill folderCard__pill--pri" :class="('p-' + String(card.priority || 'Normal').toLowerCase())">
              {{ card.priority || 'Normal' }}
            </span>
            <span class="folderCard__pill folderCard__pill--dur">
              {{ fmtH(roundedDurationHours, 2) }} h
            </span>
          </div>
        </div>
      </section>
    </template>

    <!-- Full (focus) body when not editing -->
    <section v-else class="tcard__body" @dblclick="editing = true">
      <div class="meta" v-if="card.start_utc">
        <span class="time">
          {{ new Date(card.start_utc).toLocaleTimeString([], {hour:'2-digit', minute:'2-digit'}) }} →
          <span v-if="!isRunning && card.end_utc">
            {{ new Date(card.end_utc).toLocaleTimeString([], {hour:'2-digit', minute:'2-digit'}) }}
          </span>
          <span v-else>Now</span>
        </span>
        <span class="sep">•</span>
        <span class="hours">{{ fmtH(roundedDurationHours, 2) }} h</span>
      </div>
    
      <div
        v-if="(card.description && String(card.description).trim()) || (card.notes && String(card.notes).trim())"
        class="tcard__details"
      >
        <p v-if="card.description" class="tcard__desc">{{ card.description }}</p>
        <pre v-if="card.notes" class="tcard__notes">{{ card.notes }}</pre>
      </div>
    </section>

    <footer v-if="!compact && !editing" class="tcard__foot">
      <div class="actions__icons">
        <button class="icon" type="button" @click="editing = true" title="Edit">Edit</button>
        <button class="icon" type="button" @click="isRunning ? onStop() : onStart()" :title="isRunning ? 'Stop' : 'Start'">
          {{ isRunning ? 'Stop' : 'Start' }}
        </button>
      </div>
    </footer>
  </article>
</template>

<style scoped>
  /* Knowledge Drop — Card styles: full vs compact, hover states, and small in-card controls */
  .tcard {
    display: grid;
    /* Important: avoid 1fr body growth so list cards don't inflate with empty space */
    grid-template-rows: auto auto auto; /* header | body | footer */
    grid-auto-rows: min-content;
    align-content: start;
    gap: .35rem;

    background: var(--card, #ffffff);
    border: 1px solid var(--border, #e5e7eb);
    border-radius: var(--radius, 12px);
    padding: .55rem .75rem;

    box-shadow: var(--shadow-sm, 0 1px 2px rgba(0,0,0,.06));
    transition: box-shadow .15s ease, transform .08s ease, border-color .2s ease, background .2s ease;

    overflow: hidden;
    min-height: 0;
    color: var(--text, #111827);
    position: relative;
  }
  .tcard:hover { box-shadow: var(--shadow-md, 0 6px 16px rgba(0,0,0,.08)); border-color: color-mix(in srgb, var(--border, #e5e7eb) 70%, var(--primary, #5b8cff) 30%); }
  
  .tcard__body { color: var(--text, #374151); min-height: 0; overflow: hidden; }
  .tcard__details {
    margin-top: 8px;
    display: grid;
    gap: 6px;
  }
  
  .tcard__desc {
    margin: 0;
    color: var(--text, #111827);
    font-weight: 650;
    line-height: 1.25;
  }
  
  .tcard__notes {
    margin: 0;
    padding: 8px 10px;
    border-radius: 10px;
    border: 1px solid var(--border, #e5e7eb);
    background: color-mix(in srgb, var(--panel-2, #f3f4f6) 85%, transparent);
    color: var(--text, #374151);
    font: inherit;
    white-space: pre-wrap;
    word-break: break-word;
    overflow-wrap: anywhere;
  }

/* ===== Compact (Weekly/Simple) Strict Folder Card ===== */
.tcard.compact {
  display: block;
  padding: 0;
  border: 0;
  background: transparent;
  box-shadow: none;
  min-height: 0;
  height: auto;
  overflow: visible;
}

/* Folder surface variables (easy to tune later) */
.folderCard {
  --folder-surface: var(--panel);
  --folder-border: color-mix(in srgb, var(--border) 88%, transparent);
  --folder-radius: 14px;

  position: relative;
  padding-top: 14px; /* space for tab */
}

/* Tab sits above body and shares the same surface */
.folderCard__tab {
  position: absolute;
  top: 0;
  /* left: 10px;  -- moved to modifier classes */
  height: 18px;
  min-width: 54px;   /* tighter tab footprint */
  padding: 0 10px;
  display: flex;
  align-items: center;
  gap: 8px;
  justify-content: flex-start;

  background: var(--folder-surface);
  border: 1px solid var(--folder-border);
  border-bottom: 0;
  border-top-left-radius: 14px;
  border-top-right-radius: 14px;
}

.folderCard--tab-left .folderCard__tab {
  left: 0px;
  right: auto;
}

.folderCard--tab-right .folderCard__tab {
  right: 0px;
  left: auto;
  justify-content: flex-end;
}

.folderCard__grip {
  font-size: 0.95rem;
  line-height: 1;
  opacity: 0.7;
}

.folderCard__body {
  background: var(--folder-surface);
  border: 1px solid var(--folder-border);
  border-radius: var(--folder-radius);
  padding: 14px 12px 10px 12px;

  display: grid;
  grid-template-columns: 1fr auto;
  grid-template-rows: auto auto;
  gap: 10px 10px;

  box-shadow: var(--shadow-sm);
  overflow: hidden;
}

/* When the tab is on a side, square that top corner so the tab can sit flush */
.folderCard--tab-left .folderCard__body {
  border-top-left-radius: 0;
}

.folderCard--tab-right .folderCard__body {
  border-top-right-radius: 0;
}

/* Collapsed deck entries (Option A): title strip only */
.folderCard--collapsed .folderCard__body {
  padding: 10px 12px;
  grid-template-columns: 1fr;
  grid-template-rows: auto;
  gap: 0;
}

.folderCard--collapsed .folderCard__title {
  font-size: 0.98rem;
  font-weight: 850;
}

.folderCard--collapsed .folderCard__main {
  min-width: 0;
}

.folderCard__main {
  min-width: 0;
}

  .folderCard__title {
    font-weight: 850;
    font-size: 1.05rem;
    letter-spacing: 0.01em;
    color: var(--text);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

/* Title alignment follows the tab side (so collapsed peeks are readable) */
.folderCard--tab-right .folderCard__title,
.folderCard--tab-right .folderCard__sub {
  text-align: right;
}

.folderCard__sub {
  margin-top: 2px;
  font-weight: 650;
  font-size: 0.86rem;
  color: var(--muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.folderCard__times {
  margin-top: 8px;
  display: grid;
  gap: 4px;
  font-variant-numeric: tabular-nums;
}

.folderCard__time {
  font-weight: 850;
  font-size: 1.05rem;
  color: var(--text);
  white-space: nowrap;
}

/* Right rail: stacked tools */
.folderCard__rail {
  display: grid;
  gap: 10px;
  align-content: start;
  justify-items: end;
}

.folderCard__btn {
  width: 36px;
  height: 36px;
  padding: 0;
  border-radius: 12px;
  border: 1px solid rgba(0,0,0,.12);
  background: rgba(255,255,255,.60);
  cursor: pointer;
  font-weight: 900;
  line-height: 1;
  display: grid;
  place-items: center;
  box-sizing: border-box;
  appearance: none;
  -webkit-appearance: none;
}

.folderCard__btn:hover {
  background: rgba(255,255,255,.80);
}

.folderCard__footer {
  grid-column: 1 / -1;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.folderCard__pill {
  font-size: 0.82rem;
  font-weight: 800;
  padding: 0.22rem 0.7rem;
  border-radius: 999px;
  border: 1px solid rgba(0,0,0,.12);
  background: rgba(255,255,255,.55);
  color: rgba(0,0,0,.72);
  white-space: nowrap;
}

/* Priority colors */
.folderCard__pill.p-low { background: #eef6ff; border-color: #bfdbfe; color: #1e3a8a; }
.folderCard__pill.p-normal { background: #ecfdf5; border-color: #bbf7d0; color: #065f46; }
.folderCard__pill.p-high { background: #fff7ed; border-color: #fed7aa; color: #9a3412; }
.folderCard__pill.p-critical { background: #fef2f2; border-color: #fecaca; color: #991b1b; }

.folderCard__pill--dur {
  font-variant-numeric: tabular-nums;
}
  .tcard__body p { margin: .25rem 0; word-break: break-word; overflow-wrap: anywhere; }
  
  .tcard__head { display: grid; grid-template-columns: auto 1fr auto; align-items: center; gap: .6rem; }
  .grip { cursor: default; user-select: none; font-size: 1rem; line-height: 1; opacity: .7; }
/* Folder tone palette (use stackIndex to rotate tones for stacked entries) */
.folderCard--tone-1 { --folder-surface: #bfe3ff; --folder-border: color-mix(in srgb, #3b82f6 28%, rgba(0,0,0,.12)); }
.folderCard--tone-2 { --folder-surface: #bff7ea; --folder-border: color-mix(in srgb, #14b8a6 26%, rgba(0,0,0,.12)); }
.folderCard--tone-3 { --folder-surface: #ffd7b0; --folder-border: color-mix(in srgb, #f97316 26%, rgba(0,0,0,.12)); }
.folderCard--tone-4 { --folder-surface: #ffb7b7; --folder-border: color-mix(in srgb, #ef4444 26%, rgba(0,0,0,.12)); }
  .tcard__title { display: flex; align-items: center; gap: .5rem; flex-wrap: wrap; }
  .title { font-weight: 700; letter-spacing: .2px; }
  .chip { font-size: .75rem; padding: .15rem .45rem; border-radius: 999px; background: color-mix(in srgb, var(--primary, #5b8cff) 18%, transparent); color: var(--text, #111827); border: 1px solid var(--border, #e5e7eb); }
  .tcard__title { gap: .45rem; }
  .tcard__title .title { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .hours { font-weight: 600; opacity: .9; }
  .tcard.editing {
    background: var(--panel);
    overflow: visible;
  }
  /* color-only priority dot */
  .prio-dot { width: 10px; height: 10px; border-radius: 999px; display: inline-block; border: 1px solid var(--border, #e5e7eb); }
  .prio-dot.p-low { background: #93c5fd; border-color: #93c5fd; }
  .prio-dot.p-normal { background: #86efac; border-color: #86efac; }
  .prio-dot.p-high { background: #fdba74; border-color: #fdba74; }
  .prio-dot.p-critical { background: #fca5a5; border-color: #fca5a5; }
  
  /* description clamp */
  .link.more { background: transparent; border: none; color: var(--primary, #5b8cff); padding: 0; cursor: pointer; }
  
  /* footer actions */
  .tcard__foot { display: flex; justify-content: flex-end; gap: .3rem; margin-top: 0; align-self: end; }
  
  .icon { border: 1px solid var(--border, #e5e7eb); border-radius: 8px; background: var(--panel-2, #f3f4f6); cursor: pointer; padding: .2rem .4rem; line-height: 1; }
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
  /* Default buttons for editor + full card actions only (do not affect compact deck buttons) */
  .tcard__edit button,
  .tcard__foot button {
    padding: .45rem .7rem;
    border: 1px solid var(--border, #d1d5db);
    border-radius: 8px;
    background: var(--panel-2, #f9fafb);
    cursor: pointer;
    transition: background .15s ease, border-color .15s ease, transform .06s ease;
  }

  .tcard__edit button:hover,
  .tcard__foot button:hover { background: #f0f2f6; }

  .tcard__edit button:active,
  .tcard__foot button:active { transform: translateY(1px); }

  .tcard__edit button.primary,
  .tcard__foot button.primary {
    background: linear-gradient(180deg, var(--primary, #5b8cff), var(--primary-600, #3e6dff));
    border-color: color-mix(in srgb, var(--border, #d1d5db) 40%, var(--primary, #5b8cff) 60%);
    color: #fff;
  }

  .tcard__edit button.danger,
  .tcard__foot button.danger { border-color: #ef4444; color: #b91c1c; }
  .actions__icons { display: flex; gap: .35rem; }
  
  
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