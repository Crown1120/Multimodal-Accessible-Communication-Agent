<script setup lang="ts">
import { computed } from 'vue'

import BIcon from '@/components/BIcon.vue'
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
    <div class="subtitle-head">
      <span class="subtitle-title">
        <BIcon name="captions" :size="16" />
        实时字幕
      </span>
      <span class="subtitle-state" v-if="store.recording || store.speaking">
        <span class="pulse-dot"></span>
        {{ store.recording ? '识别中' : store.speaking ? '播报中' : '' }}
      </span>
    </div>

    <!-- 错误提示 -->
    <div class="error-banner" v-if="store.lastError" role="alert">
      <BIcon name="alert" :size="15" />
      {{ store.lastError }}
    </div>

    <!-- 重复确认提示 -->
    <div class="repeat-banner" v-if="isRepeat" role="status">
      <BIcon name="bell" :size="15" />
      重要信息，请确认
    </div>

    <!-- 字幕内容 -->
    <div class="subtitle-content" v-if="store.transcript">
      <span class="speaker" v-if="speakerLabel">{{ speakerLabel }}</span>
      <span class="text">{{ store.transcript }}</span>
      <span class="cursor" v-if="store.speaking || store.recording">▍</span>
    </div>

    <!-- 占位提示 -->
    <div class="placeholder" v-else>
      <BIcon name="ear" :size="18" />
      <span>{{ store.recording ? '正在识别语音…' : '实时字幕将在此显示…' }}</span>
    </div>
  </section>
</template>

<style scoped>
.subtitle-bar {
  position: relative;
  min-height: 96px;
  margin: 14px 14px 0;
  padding: 12px 16px;
  background: linear-gradient(180deg, var(--color-surface-2), var(--color-surface));
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
  display: flex;
  flex-direction: column;
  gap: 6px;
  overflow: hidden;
}

.subtitle-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.subtitle-title {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 0.82em;
  font-weight: 600;
  color: var(--color-text-muted);
}

.subtitle-title .b-icon {
  color: var(--color-primary);
}

.subtitle-state {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 0.78em;
  font-weight: 600;
  color: var(--color-primary);
}

.pulse-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--color-primary);
  animation: pulse 1.1s ease-in-out infinite;
}

@keyframes pulse {
  0%,
  100% {
    opacity: 1;
    transform: scale(1);
  }
  50% {
    opacity: 0.4;
    transform: scale(0.8);
  }
}

/* 字幕主体：核心内容，清晰放大 */
.subtitle-content {
  display: flex;
  align-items: baseline;
  gap: 8px;
  flex-wrap: wrap;
  color: var(--color-text);
  font-size: 1.28em;
  line-height: 1.5;
  font-weight: 500;
  min-height: 1.5em;
}

.speaker {
  color: #fff;
  background: var(--color-primary-gradient);
  padding: 1px 10px;
  border-radius: var(--radius-pill);
  font-size: 0.72em;
  font-weight: 600;
  white-space: nowrap;
  flex-shrink: 0;
}

.text {
  flex: 1;
  word-break: break-word;
}

.cursor {
  animation: blink 1s step-end infinite;
  color: var(--color-primary);
  font-weight: 700;
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
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--color-text-faint);
  font-size: 0.98em;
  min-height: 1.6em;
}

.error-banner,
.repeat-banner {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 0.88em;
  padding: 5px 10px;
  border-radius: 8px;
  font-weight: 600;
}

.error-banner {
  color: var(--color-danger);
  background: var(--color-danger-soft);
}

.repeat-banner {
  color: var(--color-warning);
  background: var(--color-warning-soft);
}

/* 听障模式：字幕更大更醒目 */
.subtitle-bar.hearing {
  font-size: 1.5em;
  border-width: 2px;
  border-color: var(--color-primary);
  background: var(--color-surface);
}

.subtitle-bar.hearing .subtitle-content {
  font-size: 1.35em;
}

/* 老年模式：字幕放大 */
.subtitle-bar.elderly .subtitle-content {
  font-size: 1.4em;
}
</style>
