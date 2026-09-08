<script setup lang="ts">
import { computed } from 'vue'

import BIcon from '@/components/BIcon.vue'
import { useSessionStore } from '@/stores/session'

const store = useSessionStore()

const statusMeta = computed<{ label: string; icon: string }>(() => {
  switch (store.agentStatus) {
    case 'running':
      return { label: '执行中', icon: 'cpu' }
    case 'thinking':
      return { label: '思考中', icon: 'sparkle' }
    case 'completed':
      return { label: '已完成', icon: 'check' }
    case 'failed':
      return { label: '异常', icon: 'alert' }
    default:
      return { label: '待机', icon: 'dot' }
  }
})
</script>

<template>
  <section class="agent-status card" aria-label="Agent 执行状态">
    <div class="status-icon" :class="store.agentStatus">
      <BIcon :name="statusMeta.icon" :size="16" />
    </div>
    <div class="text">
      <div class="label">
        <span class="dot" :class="store.agentStatus"></span>
        {{ statusMeta.label }}
      </div>
      <div v-if="store.agentDetail" class="detail">{{ store.agentDetail }}</div>
      <div v-else class="detail idle">等待任务…</div>
    </div>
  </section>
</template>

<style scoped>
.agent-status {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 13px 14px;
  background: var(--color-surface);
}

.status-icon {
  width: 38px;
  height: 38px;
  border-radius: 12px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--color-surface-2);
  border: 1px solid var(--color-border);
  color: var(--color-text-muted);
}
.status-icon.running,
.status-icon.thinking {
  background: var(--color-primary-soft);
  color: var(--color-primary);
}
.status-icon.completed {
  background: var(--color-success-soft);
  color: var(--color-success);
}
.status-icon.failed {
  background: var(--color-danger-soft);
  color: var(--color-danger);
}

.text {
  min-width: 0;
}
.label {
  display: flex;
  align-items: center;
  gap: 7px;
  font-weight: 600;
  font-size: 0.92em;
}
.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--color-text-faint);
}
.dot.running,
.dot.thinking {
  background: var(--color-primary);
  animation: blink 1s infinite;
}
.dot.completed {
  background: var(--color-success);
}
.dot.failed {
  background: var(--color-danger);
}
@keyframes blink {
  50% {
    opacity: 0.25;
  }
}
.detail {
  margin-top: 2px;
  color: var(--color-text-muted);
  font-size: 0.8em;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.detail.idle {
  color: var(--color-text-faint);
}
</style>
