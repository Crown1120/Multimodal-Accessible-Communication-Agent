<script setup lang="ts">
import BIcon from '@/components/BIcon.vue'

defineProps<{
  payload: Record<string, unknown>
}>()
</script>

<template>
  <div class="task-widget">
    <div class="head">
      <span class="head-icon">
        <BIcon name="checkCircle" :size="15" />
      </span>
      <span class="head-title">任务结果</span>
    </div>

    <div class="result">{{ payload.result }}</div>
    <div v-if="payload.source" class="src">
      <BIcon name="book" :size="12" />
      原文：{{ payload.source }}
    </div>
  </div>
</template>

<style scoped>
.task-widget {
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
  padding: 12px;
  background: var(--color-surface);
  box-shadow: var(--shadow-xs);
  overflow: hidden;
  position: relative;
}
.task-widget::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 3px;
  background: var(--color-primary-gradient);
}

.head {
  display: flex;
  align-items: center;
  gap: 7px;
  font-weight: 700;
  margin-bottom: 8px;
  color: var(--color-text);
  font-size: 0.94em;
}
.head-icon {
  width: 26px;
  height: 26px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--color-success-soft);
  color: var(--color-success);
}

.result {
  font-size: 1em;
  line-height: 1.6;
}
.src {
  display: flex;
  align-items: flex-start;
  gap: 5px;
  font-size: 0.82em;
  color: var(--color-text-muted);
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px dashed var(--color-border);
  line-height: 1.5;
}
.src .b-icon {
  color: var(--color-primary);
  flex-shrink: 0;
  margin-top: 2px;
}
</style>
