<script setup lang="ts">
import { computed } from 'vue'

import BIcon from '@/components/BIcon.vue'

const props = defineProps<{
  payload: Record<string, unknown>
}>()

// 语言标签按 payload 的 source_lang / target_lang 显示。
// 旧实现把两行写死成「中文 / English」，当用户要求「翻译成中文」（英→中）时
// 标签会完全反过来，把译文标成英文。
const LANG_LABELS: Record<string, string> = { zh: '中文', en: 'English' }

function labelOf(value: unknown, fallback: string): string {
  const code = typeof value === 'string' && value ? value : fallback
  return LANG_LABELS[code] ?? code
}

const sourceLabel = computed(() => labelOf(props.payload.source_lang, 'zh'))
const targetLabel = computed(() => labelOf(props.payload.target_lang, 'en'))
</script>

<template>
  <div class="translation-widget">
    <div class="head">
      <span class="head-icon">
        <BIcon name="globe" :size="15" />
      </span>
      <span class="head-title">翻译</span>
    </div>

    <div class="pair">
      <div class="row">
        <span class="lang">{{ sourceLabel }}</span>
        <span class="text">{{ payload.source as string }}</span>
      </div>
      <div class="row en-row">
        <span class="lang">{{ targetLabel }}</span>
        <span class="text en">{{ payload.result as string }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.translation-widget {
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
  padding: 12px;
  background: var(--color-surface);
  box-shadow: var(--shadow-xs);
  overflow: hidden;
  position: relative;
}
.translation-widget::before {
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
  background: var(--color-accent-soft);
  color: var(--color-accent);
}

.pair {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.row {
  display: flex;
  align-items: baseline;
  gap: 10px;
  padding: 8px 10px;
  border-radius: 10px;
  background: var(--color-surface-2);
  border: 1px solid var(--color-border);
}
.en-row {
  background: var(--color-accent-soft);
  border-color: transparent;
}
.lang {
  font-size: 0.74em;
  font-weight: 700;
  color: var(--color-text-muted);
  min-width: 52px;
  flex-shrink: 0;
}
.text {
  flex: 1;
  line-height: 1.5;
}
.text.en {
  font-style: italic;
  color: var(--color-accent);
  font-weight: 500;
}
</style>
