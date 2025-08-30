<script setup>
import TimeBoard from './components/TimeBoard.vue'
</script>

<template>
  <TimeBoard />
</template>

<style scoped>
/* optional page tweaks */
:host, :root { --page-bg: #f5f6f8; }
:global(body) { margin: 0; background: var(--page-bg); }
</style>