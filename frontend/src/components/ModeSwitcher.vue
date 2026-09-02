<script setup lang="ts">
import type { Mode } from '@/types'
import { useSessionStore } from '@/stores/session'

const store = useSessionStore()
const modes: { value: Mode; label: string; desc: string }[] = [
  { value: 'standard', label: '标准', desc: '默认显示' },
  { value: 'hearing', label: '听障', desc: '高对比度·大字幕' },
  { value: 'elderly', label: '老年', desc: '大字体·慢速语音' },
]
</script>

<template>
  <div class="mode-switcher" role="group" aria-label="无障碍模式切换">
    <button
      v-for="m in modes"
      :key="m.value"
      :class="{ primary: store.mode === m.value }"
      :title="m.desc"
      :aria-pressed="store.mode === m.value"
      @click="store.setMode(m.value)"
    >
      {{ m.label }}
    </button>
  </div>
</template>

<style scoped>
.mode-switcher {
  display: flex;
  gap: 8px;
}
</style>
