<script setup>
import TimeBoard from './components/TimeBoard.vue'
</script>

<template>
  <TimeBoard />
</template>

<style scoped>
:global(:root) {
  /* Light, high-contrast palette */
  --bg: #f6f7fb;
  --panel: #ffffff;
  --panel-2: #f3f4f6;
  --text: #0f172a;     /* slate-900 */
  --muted: #475569;    /* slate-600 */
  --border: #95b4db;   /* slate-200 */
  --primary: #2563eb;  /* blue-600 */
  --primary-600: #1d4ed8;
  --accent: #06b6d4;   /* cyan-500 */
  --radius: 12px;
  --shadow-sm: 0 1px 2px rgba(16,24,40,.06);
  --shadow-md: 0 8px 24px rgba(16,24,40,.08);
  --container: 1280px; /* app max width */
  --btn-blue-bg: #eaf2ff;
  --btn-blue-bg-hover: #dbe7ff;
}
:global(html, body, #app) { height: 100%; }
:global(body) {
  margin: 0; background: var(--bg); color: var(--text);
  -webkit-font-smoothing: antialiased; -moz-osx-font-smoothing: grayscale;
  font: 500 15px/1.5 Inter, ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, "Helvetica Neue", Arial;
}
:global(#app) { min-height: 100dvh; }
@media (prefers-color-scheme: dark) {
  :global(:root) {
    --bg:#0b1220; --panel:#0f172a; --panel-2:#111827;
    --text:#e5e7eb; --muted:#94a3b8; --border:#243b5a;
    --primary:#60a5fa; --primary-600:#3b82f6; --accent:#22d3ee;
    --btn-blue-bg:#13223f; --btn-blue-bg-hover:#0f1b33;
  }
}
</style>