<script setup>
import { ref, onErrorCaptured, computed, onMounted } from 'vue'
import TimeBoard from './components/TimeBoard.vue'
// Optional debug/simple view: visit http://localhost:5173/?sheet=1
// to render the lightweight TimeSheet page instead of the board
import TimeSheet from './components/TimeSheet.vue'
import { API_BASE, apiFetch } from './lib/api'

const ready = ref(false)
onMounted(async () => {
  try {
    const r = await apiFetch(`${API_BASE}/api/auth/me`)
    if (r.ok) {
      const me = await r.json()
      localStorage.setItem('logger.userId', me.id)
    }
  } catch {}
  ready.value = true
})

const err = ref(null)
onErrorCaptured((e) => { err.value = e; console.error(e); return false })

const showSheet = computed(() => new URLSearchParams(location.search).get('sheet') === '1')
</script>

<template>
  <div>
    <div v-if="err" class="fatal">
      <h1>UI error</h1>
      <pre class="pre">{{ String(err && (err.message || err)) }}</pre>
      <p>Check the browser console for stack traces.</p>
    </div>
    <TimeSheet v-else-if="showSheet" />
    <TimeBoard v-else />
  </div>
</template>

<style scoped>
:global(:root) {
  /* Light, softer palette */
  --bg: #f7f9f8;
  --panel: #ffffff;
  --panel-2: #f2f5f4;
  --text: #0c1b1b;      /* deep teal-gray */
  --muted: #5c6b6b;     /* desaturated slate/teal */
  --border: #c7d8d5;    /* soft cool gray-green */
  --primary: #2f8f83;   /* teal 600 */
  --primary-600: #2a7c73;
  --accent: #86d2c1;    /* mint accent */
  --radius: 12px;
  --shadow-sm: 0 1px 2px rgba(16,24,40,.06);
  --shadow-md: 0 8px 24px rgba(16,24,40,.08);
  --container: 1280px; /* app max width */
  --btn-blue-bg: #e8f3f0;         /* soft minty button bg */
  --btn-blue-bg-hover: #dbeae6;   /* hover state */
}
:global(html, body, #app) { height: 100%; }
:global(body) {
  margin: 0; background: var(--bg); color: var(--text);
  -webkit-font-smoothing: antialiased; -moz-osx-font-smoothing: grayscale;
  font: 500 15px/1.5 Inter, ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, "Helvetica Neue", Arial;
}
:global(#app) { min-height: 100dvh; }
:global(:root[data-theme="dark"]) {
  /* Dark, low-strain palette */
  --bg:#0e1414;       /* very dark teal-gray */
  --panel:#121a1a;    /* card background */
  --panel-2:#0f1717;  /* subtle panel */
  --text:#e6f2f0;     /* soft near-white */
  --muted:#9db5b1;    /* muted labels */
  --border:#20302f;   /* cool border */
  --primary:#7fd1c3;  /* soft teal */
  --primary-600:#63b5a8;
  --accent:#b9eadf;   /* pale mint */
  --btn-blue-bg:#16211f;        /* button surface */
  --btn-blue-bg-hover:#101917;  /* hover */
}

.fatal { padding:16px; color:#991b1b; background:#fee2e2; border:1px solid #fecaca; border-radius: 10px; margin:16px; }
.pre { white-space: pre-wrap; font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace; }
</style>