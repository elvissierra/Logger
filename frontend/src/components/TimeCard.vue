
<script setup>
import { ref, watch, computed, onMounted } from 'vue'

const props = defineProps({
  card: { type: Object, required: true },
  openOnMount: { type: Boolean, default: false }
})
const emit = defineEmits(['save', 'delete'])

const editing = ref(false)
const local = ref(structuredClone(props.card))
watch(() => props.card, (v) => { local.value = structuredClone(v) }, { deep: true })
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
// Auto-open editor for brand-new cards or when parent requests it
onMounted(() => {
  const tmp = props.card && String(props.card.id || '').startsWith('tmp_')
  if (props.openOnMount || tmp) {
    editing.value = true
    local.value.start_local = local.value.start_local || toLocalInput(local.value.start_utc)
    local.value.end_local   = local.value.end_local   || toLocalInput(local.value.end_utc)
  }
})
// ISO -> datetime-local (input value)
function toLocalInput(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  d.setMinutes(d.getMinutes() - d.getTimezoneOffset())
  return d.toISOString().slice(0, 16) // YYYY-MM-DDTHH:mm
}
// datetime-local -> ISO (UTC)
function fromLocalInput(localStr) {
  if (!localStr) return ''
  const d = new Date(localStr)
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString()
}

const durationHours = computed(() => {
  if (!props.card.start_utc || !props.card.end_utc) return 0
  const s = new Date(props.card.start_utc).getTime()
  const e = new Date(props.card.end_utc).getTime()
  return Math.max(0, (e - s) / 3600000)
})

function onSave() {
  const payload = {
    ...local.value,
    // map UI -> API fields
    project_code: local.value.projectCode,
    activity: local.value.activity,
    notes: [local.value.description, local.value.notes].filter(Boolean).join('\n'),
    start_utc: fromLocalInput(local.value.start_local || toLocalInput(local.value.start_utc)),
    end_utc: fromLocalInput(local.value.end_local || toLocalInput(local.value.end_utc)),
  }
  emit('save', payload)
  editing.value = false
}
function onDelete() { emit('delete', props.card) }
</script>

<template>
  <article class="tcard" :class="{ editing }">
    <header class="tcard__head">
      <span class="handle" title="Drag to reorder" aria-label="Drag handle">☰</span>
      <div class="tcard__title">
        <strong class="title">{{ card.jobTitle || card.projectCode || 'Untitled' }}</strong>
        <span class="chip" v-if="card.activity">{{ card.activity }}</span>
      </div>
      <button class="icon" title="Edit" aria-label="Edit" @click="editing = !editing">✎</button>
    </header>

    <section v-if="!editing" class="tcard__body" @dblclick="editing = true">
      <p class="desc" v-if="card.description">{{ card.description }}</p>
      <p class="notes" v-if="card.notes"><em>{{ card.notes }}</em></p>

      <div class="meta" v-if="card.start_utc && card.end_utc">
        <span class="time">
          {{ new Date(card.start_utc).toLocaleTimeString([], {hour:'2-digit', minute:'2-digit'}) }} →
          {{ new Date(card.end_utc).toLocaleTimeString([], {hour:'2-digit', minute:'2-digit'}) }}
        </span>
        <span class="sep">•</span>
        <span class="hours">{{ durationHours.toFixed(2) }} h</span>
      </div>
    </section>

    <section v-else class="tcard__edit">
      <div class="grid">
        <label>Job Title
          <input v-model="local.jobTitle" placeholder="Bridge Inspection" />
        </label>
        <label>Project Code
          <input v-model="local.projectCode" placeholder="PJ-001" />
        </label>
        <label>Activity
          <input v-model="local.activity" placeholder="Paperwork / Field Work / Travel" />
        </label>
        <label>Description
          <textarea v-model="local.description" rows="2" placeholder="What you worked on"></textarea>
        </label>
        <label>Notes
          <textarea v-model="local.notes" rows="2" placeholder="Optional notes"></textarea>
        </label>
        <div class="row">
          <label>Start
            <input type="datetime-local" v-model="local.start_local" />
          </label>
          <label>End
            <input type="datetime-local" v-model="local.end_local" />
          </label>
        </div>
      </div>
      <div class="actions">
        <button type="button" class="primary" @click="onSave">Save</button>
        <button type="button" class="secondary" @click="editing=false">Cancel</button>
        <button type="button" class="danger" @click="onDelete">Delete</button>
      </div>
    </section>
  </article>
</template>

<style scoped>
.tcard {
  display: grid; gap: .55rem;
  background: var(--card, #ffffff);
  border: 1px solid var(--border, #e5e7eb);
  border-radius: var(--radius, 12px);
  padding: .75rem .9rem;
  box-shadow: var(--shadow-sm, 0 1px 2px rgba(0,0,0,.06));
  transition: box-shadow .15s ease, transform .08s ease, border-color .2s ease, background .2s ease;
}
.tcard:hover { box-shadow: var(--shadow-md, 0 6px 16px rgba(0,0,0,.08)); border-color: color-mix(in srgb, var(--border, #e5e7eb) 70%, var(--primary, #5b8cff) 30%); }
.tcard.editing { background: var(--panel, #f6f7fb); }

.tcard__head { display: grid; grid-template-columns: auto 1fr auto; align-items: center; gap: .6rem; }
.handle { cursor: grab; user-select: none; font-size: 1rem; line-height: 1; opacity: .7; }
.tcard__title { display: flex; align-items: center; gap: .5rem; flex-wrap: wrap; }
.title { font-weight: 700; letter-spacing: .2px; }
.chip { font-size: .75rem; padding: .15rem .45rem; border-radius: 999px; background: color-mix(in srgb, var(--primary, #5b8cff) 18%, transparent); color: var(--text, #111827); border: 1px solid var(--border, #e5e7eb); }
.icon { border: 1px solid var(--border, #e5e7eb); border-radius: 8px; background: var(--panel-2, #f3f4f6); cursor: pointer; padding: .25rem .4rem; }
.icon:hover { background: #e9eef7; }

.tcard__body { color: var(--text, #374151); }
.desc { margin: .2rem 0; color: var(--text, #111827); }
.notes { margin: .2rem 0; color: var(--muted, #6b7280); }
.meta { display: flex; align-items: center; gap: .4rem; color: var(--muted, #6b7280); font-size: .9rem; }
.sep { opacity: .5; }

.tcard__edit .grid { display: grid; gap: .5rem; }
.tcard__edit label { display: grid; gap: .25rem; }
.tcard__edit .row { display: grid; grid-template-columns: 1fr 1fr; gap: .5rem; }
input, textarea, button { font: inherit; color: var(--text, #111827); }
input, textarea { padding: .5rem .6rem; border: 1px solid var(--border, #d1d5db); border-radius: 8px; background: var(--panel, #ffffff); }
.actions { display: flex; gap: .5rem; justify-content: flex-end; }
button {
  padding: .45rem .7rem; border: 1px solid var(--border, #d1d5db); border-radius: 8px; background: var(--panel-2, #f9fafb);
  cursor: pointer; transition: background .15s ease, border-color .15s ease, transform .06s ease;
}
button:hover { background: #f0f2f6; }
button:active { transform: translateY(1px); }
button.primary { background: linear-gradient(180deg, var(--primary, #5b8cff), var(--primary-600, #3e6dff)); border-color: color-mix(in srgb, var(--border, #d1d5db) 40%, var(--primary, #5b8cff) 60%); color: #fff; }
button.danger { border-color: #ef4444; color: #b91c1c; }
</style>