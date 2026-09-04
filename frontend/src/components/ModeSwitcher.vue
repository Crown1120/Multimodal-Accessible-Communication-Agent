<script setup lang="ts">
import BIcon from '@/components/BIcon.vue'
import type { Mode } from '@/types'
import { useSessionStore } from '@/stores/session'

const store = useSessionStore()
const modes: { value: Mode; label: string; desc: string; icon: 'eye' | 'ear' | 'user' }[] = [
  { value: 'standard', label: '标准', desc: '默认显示', icon: 'eye' },
  { value: 'hearing', label: '听障', desc: '高对比度·大字幕', icon: 'ear' },
  { value: 'elderly', label: '老年', desc: '大字体·慢速语音', icon: 'user' },
]
</script>

<template>
  <div class="mode-switcher" role="group" aria-label="无障碍模式切换">
    <button
      v-for="m in modes"
      :key="m.value"
      class="mode-btn"
      :class="{ active: store.mode === m.value }"
      :title="m.desc"
      :aria-pressed="store.mode === m.value"
      @click="store.setMode(m.value)"
    >
      <BIcon :name="m.icon" :size="15" />
      <span>{{ m.label }}</span>
    </button>
  </div>
</template>

<style scoped>
.mode-switcher {
  display: inline-flex;
  gap: 3px;
  padding: 3px;
  background: var(--color-surface-2);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-pill);
}

.mode-btn {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 5px 13px;
  border: none;
  background: transparent;
  border-radius: var(--radius-pill);
  color: var(--color-text-muted);
  font-size: 0.86em;
  font-weight: 500;
}
.mode-btn:hover:not(:disabled) {
  color: var(--color-primary);
  background: transparent;
}
.mode-btn.active {
  background: var(--color-primary-gradient);
  color: #fff;
  box-shadow: var(--shadow-primary);
}
[data-mode='hearing'] .mode-btn.active,
[data-contrast='on'] .mode-btn.active {
  color: #000;
}
</style>
