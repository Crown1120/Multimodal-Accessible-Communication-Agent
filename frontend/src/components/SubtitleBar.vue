<script setup lang="ts">
// 实时字幕条：ASR 增量识别与数字人播报文本的可访问展示。
//
// 无障碍要点：
// - role="status" + aria-live="polite"：屏幕阅读器播报实时内容（本项目此前完全没有 live region）；
// - aria-atomic="false"：流式追加时只播报变化部分，避免整段重读；
// - 字幕文本可选中复制，供听障用户留存信息。
import { computed } from 'vue'

import BIcon from '@/components/BIcon.vue'
import { useSessionStore } from '@/stores/session'

const store = useSessionStore()

const props = withDefaults(
  defineProps<{
    collapsed?: boolean
  }>(),
  { collapsed: false },
)
const emit = defineEmits<{
  toggle: []
}>()

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
const toggleLabel = computed(() => (props.collapsed ? '展开沟通记录栏' : '收起沟通记录栏'))
</script>

<template>
  <div class="subtitle-bar" :class="{ active: hasTranscript, collapsed: props.collapsed }">
    <div class="subtitle-header">
      <div class="subtitle-label">
        <span class="dot" aria-hidden="true"></span>
        <span>实时字幕</span>
        <span v-if="speakerLabel" class="speaker">· {{ speakerLabel }}</span>
      </div>
      <button
        class="subtitle-toggle"
        type="button"
        :aria-label="toggleLabel"
        :aria-expanded="!props.collapsed"
        aria-controls="conversation-panel"
        :title="toggleLabel"
        @click="emit('toggle')"
      >
        <BIcon :name="props.collapsed ? 'arrowLeft' : 'arrowRight'" :size="16" :stroke-width="2" />
      </button>
    </div>
    <p
      id="live-subtitle-text"
      class="subtitle-text"
      role="status"
      aria-live="polite"
      aria-atomic="false"
    >
      {{ hasTranscript ? store.transcript : '等待语音或回复…' }}
    </p>
  </div>
</template>

<style scoped>
.subtitle-bar {
  flex-shrink: 0;
  width: 100%;
  box-sizing: border-box;
  padding: 10px 18px 12px;
  border-bottom: 1px solid var(--color-border);
  background: var(--color-surface);
  transition:
    width 0.2s var(--ease-out),
    padding 0.2s var(--ease-out),
    background-color 0.2s var(--ease-out);
}
.subtitle-bar.active {
  background: var(--color-primary-soft);
}

.subtitle-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.subtitle-label {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 0.76em;
  font-weight: 600;
  color: var(--color-text-muted);
  min-width: 0;
}
.subtitle-toggle {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex: 0 0 auto;
  width: 30px;
  height: 30px;
  padding: 0;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--color-text-muted);
  cursor: pointer;
  transition:
    background-color 0.15s var(--ease-out),
    color 0.15s var(--ease-out),
    border-color 0.15s var(--ease-out);
}
.subtitle-toggle:hover {
  background: var(--color-primary-soft);
  border-color: var(--color-primary);
  color: var(--color-primary);
}
.subtitle-toggle:focus-visible {
  outline: 3px solid color-mix(in srgb, var(--color-primary) 35%, transparent);
  outline-offset: 2px;
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
  margin-top: 4px;
  font-size: 1.05em;
  line-height: 1.6;
  color: var(--color-text);
  min-height: 1.6em;
  word-break: break-word;
  white-space: pre-wrap;
  user-select: text;
}
.subtitle-bar.collapsed {
  align-self: flex-end;
  width: 44px;
  padding: 6px 6px 6px 5px;
  border: 1px solid var(--color-border);
  border-right: 0;
  border-radius: 10px 0 0 10px;
  background: var(--color-surface);
  box-shadow: var(--shadow-sm);
}
.subtitle-bar.collapsed .subtitle-text {
  display: none;
}
.subtitle-bar.collapsed .subtitle-label {
  display: none;
}
.subtitle-bar.collapsed .subtitle-header {
  justify-content: flex-end;
}
.subtitle-bar.collapsed .subtitle-toggle {
  width: 32px;
  height: 32px;
  border: 0;
  border-radius: 6px;
  background: var(--color-surface-2);
}
.subtitle-bar.collapsed .subtitle-toggle:hover {
  background: var(--color-primary-soft);
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
