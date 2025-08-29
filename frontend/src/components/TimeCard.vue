<script setup>
import { ref, watch, computed } from 'vue'

const props = defineProps({ card: { type: Object, required: true } })
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
  <article class="card">
    <header class="card__header">
      <span class="handle" title="Drag to reorder">⠿</span>
      <strong class="title">{{ card.jobTitle || card.projectCode || 'Untitled' }}</strong>
      <span class="activity">{{ card.activity || '—' }}</span>
    </header>

    <section v-if="!editing" class="card__body" @dblclick="editing = true">
      <p class="desc" v-if="card.description">{{ card.description }}</p>
      <p class="notes" v-if="card.notes"><em>{{ card.notes }}</em></p>
      <div class="times" v-if="card.start_utc && card.end_utc">
        <small>
          {{ new Date(card.start_utc).toLocaleString() }} →
          {{ new Date(card.end_utc).toLocaleString() }}
          ({{ durationHours.toFixed(2) }} h)
        </small>
      </div>
    </section>

    <section v-else class="card__edit">
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
      <div class="actions">
        <button type="button" @click="onSave">Save</button>
        <button type="button" class="secondary" @click="editing=false">Cancel</button>
        <button type="button" class="danger" @click="onDelete">Delete</button>
      </div>
    </section>

    <footer class="card__footer" v-if="!editing">
      <button type="button" @click="editing = true">Edit</button>
      <button type="button" class="danger" @click="onDelete">Delete</button>
    </footer>
  </article>
</template>

<style scoped>
.card { display: grid; gap: .5rem; background: #fff; border: 1px solid #e5e7eb; border-radius: 12px; padding: .75rem .9rem; box-shadow: 0 1px 2px rgba(0,0,0,.05); }
.card__header { display: grid; grid-template-columns: auto 1fr auto; align-items: center; gap: .5rem; }
.handle { cursor: grab; user-select: none; font-size: 1.1rem; line-height: 1; opacity: .6; }
.title { font-size: 1rem; }
.activity { font-size: .85rem; color: #6b7280; }
.card__body { color: #374151; }
.desc { margin: .25rem 0; }
.notes { margin: .25rem 0; color: #6b7280; }
.card__edit label { display: grid; gap: .25rem; margin-bottom: .5rem; }
.row { display: grid; grid-template-columns: 1fr 1fr; gap: .5rem; }
input, textarea, button { font: inherit; }
input, textarea { padding: .5rem .6rem; border: 1px solid #d1d5db; border-radius: 8px; }
.actions { display: flex; gap: .5rem; justify-content: flex-end; }
button { padding: .45rem .7rem; border: 1px solid #d1d5db; border-radius: 8px; background: #f9fafb; cursor: pointer; }
button.secondary { background: #fff; }
button.danger { border-color: #ef4444; color: #b91c1c; }
</style>