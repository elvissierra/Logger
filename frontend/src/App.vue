
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

const view = ref(
  new URLSearchParams(location.search).get('sheet') === '1' ? 'sheet' : 'board'
)
const showSheet = computed(() => view.value === 'sheet')

function setView (mode) {
  view.value = mode === 'sheet' ? 'sheet' : 'board'
  const url = new URL(window.location.href)
  if (view.value === 'sheet') {
    url.searchParams.set('sheet', '1')
  } else {
    url.searchParams.delete('sheet')
  }
  window.history.replaceState({}, '', url.toString())
}

</script>


<template>
  <div class="shell" v-if="ready">
    <header class="shell__header">
      <div class="shell__brand">
        <div class="shell__logo" aria-hidden="true">⏱</div>
        <div class="shell__titles">
          <h1 class="shell__title">Logger</h1>
          <p class="shell__subtitle">Plan your week, log your work, see your time clearly.</p>
        </div>
      </div>
      <nav class="shell__nav" aria-label="View switch">
        <button
          type="button"
          class="shell__navbtn"
          :class="{ active: !showSheet }"
          @click="setView('board')"
        >
          Board
        </button>
        <button
          type="button"
          class="shell__navbtn"
          :class="{ active: showSheet }"
          @click="setView('sheet')"
        >
          Timesheet
        </button>
      </nav>
    </header>

    <main class="shell__main">
      <div v-if="err" class="fatal">
        <h2>UI error</h2>
        <pre class="pre">{{ String(err && (err.message || err)) }}</pre>
        <p>Check the browser console for stack traces.</p>
      </div>
      <TimeSheet v-else-if="showSheet" />
      <TimeBoard v-else />
    </main>
  </div>

  <div v-else class="shell shell--loading">
    <div class="shell__loading">
      <div class="shell__spinner" aria-hidden="true"></div>
      <p>Loading Logger…</p>
    </div>
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

.shell {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}
.shell__header {
  position: sticky;
  top: 0;
  z-index: 20;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 14px 24px;
  background: var(--bg);
  border-bottom: 1px solid var(--border);
  box-shadow: 0 4px 12px rgba(15, 23, 42, 0.03);
}
.shell__brand {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}
.shell__logo {
  width: 36px;
  height: 36px;
  border-radius: 10px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 1.2rem;
  background: var(--btn-blue-bg);
  color: var(--primary);
  border: 1px solid var(--border);
  box-shadow: var(--shadow-sm);
}
.shell__titles {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}
.shell__title {
  margin: 0;
  font-size: 1.6rem;              /* make the app name clearly dominant */
  font-weight: 780;
  letter-spacing: 0.03em;         /* subtle brand-like tracking */
  color: var(--primary);          /* tie the brand to the primary accent */
}
.shell__subtitle {
  margin: 0;
  font-size: 0.86rem;
  color: var(--muted);
}
.shell__nav {
  display: inline-flex;
  gap: 8px;
  align-items: center;
}
.shell__navbtn {
  padding: 0.4rem 0.9rem;
  border-radius: 999px;
  border: 1px solid var(--border);
  background: var(--panel);
  color: var(--muted);
  font-size: 0.9rem;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.15s ease, border-color 0.15s ease, color 0.15s ease, transform 0.06s ease;
}
.shell__navbtn:hover {
  background: var(--btn-blue-bg-hover);
  transform: translateY(1px);
}
.shell__navbtn.active {
  background: var(--btn-blue-bg);
  color: var(--primary);
  border-color: color-mix(in srgb, var(--border) 50%, var(--primary) 50%);
}
.shell__main {
  flex: 1;
  padding: 12px 18px 24px;
}
.shell--loading {
  display: flex;
  align-items: center;
  justify-content: center;
}
.shell__loading {
  display: grid;
  gap: 10px;
  place-items: center;
  padding: 24px;
  background: var(--panel);
  border-radius: var(--radius);
  box-shadow: var(--shadow-md);
  border: 1px solid var(--border);
}
.shell__spinner {
  width: 24px;
  height: 24px;
  border-radius: 999px;
  border: 3px solid var(--border);
  border-top-color: var(--primary);
  animation: shell-spin 0.9s linear infinite;
}
@keyframes shell-spin {
  to { transform: rotate(360deg); }
}
</style>