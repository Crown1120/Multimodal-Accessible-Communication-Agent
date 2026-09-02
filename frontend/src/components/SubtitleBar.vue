<script setup lang="ts">
import { computed } from 'vue'

import { useSessionStore } from '@/stores/session'

const store = useSessionStore()

const speakerLabel = computed(() => {
  const s = store.transcriptSpeaker
  if (!s) return ''
  if (s === 'assistant' || s === 'digital_human') return '数字人'
  if (s === 'staff') return '工作人员'
  return s
})

const isRepeat = computed(() => store.needRepeat)
</script>

<template>
  <section
    class="subtitle-bar"
    :class="store.mode"
    aria-live="polite"
    aria-label="实时字幕"
  >
    <!-- 错误提示 -->
    <div class="error-banner" v-if="store.lastError" role="alert">
      ⚠️ {{ store.lastError }}
    </div>

    <!-- 重复确认提示 -->
    <div class="repeat-banner" v-if="isRepeat" role="status">
      🔔 重要信息，请确认
    </div>

    <!-- 字幕内容 -->
    <div class="subtitle-content" v-if="store.transcript">
      <span class="speaker" v-if="speakerLabel">【{{ speakerLabel }}】</span>
      <span class="text">{{ store.transcript }}</span>
      <span class="cursor" v-if="store.speaking || store.recording">▎</span>
    </div>

    <!-- 占位提示 -->
    <div class="placeholder" v-else>
      {{ store.recording ? '正在识别语音…' : '实时字幕将在此显示…' }}
    </div>
  </section>
</template>

<style scoped>
.subtitle-bar {
  min-height: 72px;
  padding: 14px 18px;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
  font-size: 1.15em;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

/* 听障模式：高对比度、大字号 */
.subtitle-bar.hearing {
  font-size: 1.6em;
  font-weight: 500;
  border-width: 2px;
}

/* 老年模式：暖色背景、大字号 */
.subtitle-bar.elderly {
  font-size: 1.5em;
  font-weight: 500;
}

.subtitle-content {
  display: flex;
  align-items: baseline;
  gap: 6px;
  flex-wrap: wrap;
  color: var(--color-text);
}
.speaker {
  color: var(--color-primary);
  font-weight: 600;
  white-space: nowrap;
}
.text {
  flex: 1;
}
.cursor {
  animation: blink 1s step-end infinite;
  color: var(--color-primary);
}
@keyframes blink {
  0%,
  50% {
    opacity: 1;
  }
  51%,
  100% {
    opacity: 0;
  }
}
.placeholder {
  color: var(--color-text-muted);
}
.error-banner {
  color: var(--color-danger);
  font-size: 0.9em;
  padding: 4px 8px;
  background: rgba(229, 72, 77, 0.1);
  border-radius: 6px;
}
.repeat-banner {
  color: var(--color-warning);
  font-size: 0.9em;
  font-weight: 600;
  padding: 4px 8px;
  background: rgba(245, 166, 35, 0.12);
  border-radius: 6px;
}
</style>
