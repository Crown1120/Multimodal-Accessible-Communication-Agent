<script setup lang="ts">
import { useSessionStore } from '@/stores/session'

const store = useSessionStore()
</script>

<template>
  <section class="agent-status" aria-label="Agent 执行状态">
    <div class="dot" :class="store.agentStatus"></div>
    <div class="text">
      <div class="label">{{ store.agentStatus }}</div>
      <div class="detail" v-if="store.agentDetail">{{ store.agentDetail }}</div>
    </div>
  </section>
</template>

<style scoped>
.agent-status {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 8px;
}
.dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: var(--color-text-muted);
}
.dot.running,
.dot.thinking {
  background: var(--color-primary);
  animation: blink 1s infinite;
}
.dot.completed {
  background: var(--color-accent);
}
.dot.failed {
  background: var(--color-danger);
}
@keyframes blink {
  50% {
    opacity: 0.3;
  }
}
.label {
  text-transform: capitalize;
  font-size: 0.85em;
}
.detail {
  color: var(--color-text-muted);
  font-size: 0.8em;
}
</style>
