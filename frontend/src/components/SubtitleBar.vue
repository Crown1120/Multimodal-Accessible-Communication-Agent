<script setup lang="ts">
// 实时字幕条：ASR 增量识别与数字人播报文本的可访问展示。
//
// 无障碍要点：
// - role="status" + aria-live="polite"：屏幕阅读器播报实时内容（本项目此前完全没有 live region）；
// - aria-atomic="false"：流式追加时只播报变化部分，避免整段重读；
// - 字幕文本可选中复制，供听障用户留存信息。
import { computed } from 'vue'

import { useSessionStore } from '@/stores/session'

const store = useSessionStore()

const speakerLabel = computed(() => {
  switch (store.transcriptSpeaker) {
    case 'assistant':
      return 'Bridge 助理'
    case 'staff':
      return '工作人员'
    case 'user':
      return '用户'
    default:
      return store.transcriptSpeaker || ''
  }
})

const hasTranscript = computed(() => store.transcript.trim().length > 0)
</script>

<template>
  <div class="subtitle-bar" :class="{ active: hasTranscript }">
    <div class="subtitle-label">
      <span class="dot" aria-hidden="true"></span>
      <span>实时字幕</span>
      <span v-if="speakerLabel" class="speaker">· {{ speakerLabel }}</span>
    </div>
    <p class="subtitle-text" role="status" aria-live="polite" aria-atomic="false">
      {{ hasTranscript ? store.transcript : '等待语音或回复…' }}
    </p>
  </div>
</template>

<style scoped>
.subtitle-bar {
  flex-shrink: 0;
  padding: 10px 18px 12px;
  border-bottom: 1px solid var(--color-border);
  background: var(--color-surface);
  transition: background-color 0.2s var(--ease-out);
}
.subtitle-bar.active {
  background: var(--color-primary-soft);
}

.subtitle-label {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 0.76em;
  font-weight: 600;
  color: var(--color-text-muted);
  margin-bottom: 4px;
}
.subtitle-label .speaker {
  font-weight: 500;
  color: var(--color-text-faint);
}
.dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--color-text-faint);
}
.subtitle-bar.active .dot {
  background: var(--color-primary);
  animation: livePulse 1.4s ease-in-out infinite;
}
@keyframes livePulse {
  0%,
  100% {
    opacity: 1;
    transform: scale(1);
  }
  50% {
    opacity: 0.45;
    transform: scale(0.8);
  }
}

.subtitle-text {
  margin: 0;
  font-size: 1.05em;
  line-height: 1.6;
  color: var(--color-text);
  min-height: 1.6em;
  word-break: break-word;
  white-space: pre-wrap;
  user-select: text;
}
.subtitle-bar:not(.active) .subtitle-text {
  color: var(--color-text-faint);
}

/* 高对比度 / 听障模式：加大字号与对比度 */
[data-contrast='on'] .subtitle-text,
[data-mode='hearing'] .subtitle-text {
  color: #fff;
  font-weight: 500;
}
[data-font-size='large'] .subtitle-text,
[data-mode='hearing'] .subtitle-text,
[data-mode='elderly'] .subtitle-text {
  font-size: 1.2em;
}
</style>
