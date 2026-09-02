<script setup lang="ts">
defineProps<{
  payload: Record<string, unknown>
}>()
</script>

<template>
  <div class="task-widget">
    <div class="head">
      <span class="icon">✅</span>
      <span>任务结果</span>
    </div>
    <div class="result">{{ payload.result }}</div>
    <div class="src" v-if="payload.source">原文：{{ payload.source }}</div>
  </div>
</template>

<style scoped>
.task-widget {
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
  padding: 12px;
  background: var(--color-surface);
}
.head {
  display: flex;
  align-items: center;
  gap: 6px;
  font-weight: 600;
  margin-bottom: 8px;
  color: var(--color-primary);
}
.result {
  font-size: 1.05em;
}
.src {
  font-size: 0.85em;
  color: var(--color-text-muted);
  margin-top: 6px;
}
</style>
