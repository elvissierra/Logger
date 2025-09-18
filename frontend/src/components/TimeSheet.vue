<template>
  <section class="wrapper">
    <h1>Weekly Time Entries</h1>
 
    <!-- Simple form posts raw fields to /api/time-entries/; use ISO UTC times (e.g., 2025-08-29T14:00:00Z). -->
    <form @submit.prevent="create">
      <fieldset>
        <legend>New Entry</legend>
        <label>
          Project Code
          <input v-model="form.project_code" placeholder="PJ-001" required />
        </label>
        <label>
          Activity
          <input v-model="form.activity" placeholder="Paperwork" required />
        </label>
        <label>
          Start (UTC ISO)
          <input v-model="form.start_utc" placeholder="2025-08-29T14:00:00Z" required />
        </label>
        <label>
          End (UTC ISO)
          <input v-model="form.end_utc" placeholder="2025-08-29T16:30:00Z" required />
        </label>
        <label>
          Notes
          <input v-model="form.notes" placeholder="Description (optional)" />
        </label>
        <button type="submit">Create</button>
      </fieldset>
    </form>

    <div class="entries">
      <h2>Entries</h2>
      <button @click="load">Refresh</button>
      <ul>
        <li v-for="e in entries" :key="e.id">
          <strong>{{ e.project_code }} — {{ e.activity }}</strong>
          <div>{{ e.start_utc }} → {{ e.end_utc }} ({{ (e.seconds/3600).toFixed(2) }} h)</div>
          <small>{{ e.notes }}</small>
          <div class="row-actions">
            <button @click="remove(e.id)">Delete</button>
          </div>
        </li>
      </ul>
    </div>
  </section>
</template>

<script setup>
/**
 * Knowledge Drop — TimeSheet.vue (API harness)
 *
 * Purpose
 * - Minimal page to exercise the time-entries API without the full board UI.
 * - Useful for debugging CORS/cookies and verifying CRUD quickly.
 *
 * How it ties in
 * - Shares the same apiFetch refresh logic as the main app, so auth behavior matches the board.
 * - Lets you create and delete entries with raw ISO strings (UTC) to confirm backend behavior.
 */
import { reactive, ref, onMounted } from 'vue'
import { API_BASE, apiFetch, getCsrf } from '../lib/api'


const entries = ref([])
const form = reactive({
  project_code: 'PJ-001',
  activity: 'Paperwork',
  start_utc: '',
  end_utc: '',
  notes: ''
})

async function load () {
  const res = await apiFetch(`${API_BASE}/api/time-entries/`)
  entries.value = await res.json()
}
async function create () {
  const res = await apiFetch(`${API_BASE}/api/time-entries/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': getCsrf() },
    body: JSON.stringify({
    project_code: form.project_code,
    activity: form.activity,
    start_utc: form.start_utc,
    end_utc: form.end_utc,
    notes: form.notes
    })
  })
  if (!res.ok) {
    const msg = await res.text()
    alert(`Failed to create: ${msg}`)
    return
  }
  Object.assign(form, { start_utc: '', end_utc: '', notes: '' })
  await load()
}
async function remove (id) {
  const res = await apiFetch(`${API_BASE}/api/time-entries/${id}`, { method: 'DELETE', headers: { 'X-CSRF-Token': getCsrf() } })
  if (!res.ok) {
    alert('Failed to delete')
    return
  }
  await load()
}
onMounted(load)
</script>

<style scoped>
/* Knowledge Drop — Basic layout styles for the harness; not used by the main board. */
.wrapper { max-width: 760px; margin: 2rem auto; padding: 0 1rem; }
form fieldset { display: grid; gap: .5rem; border: 1px solid #ddd; padding: 1rem; }
label { display: grid; gap: .25rem; }
input { padding: .5rem; }
button { padding: .5rem .75rem; cursor: pointer; }
ul { list-style: none; padding: 0; }
li { padding: .75rem 0; border-bottom: 1px solid #eee; }
.row-actions { margin-top: .25rem; }
</style>