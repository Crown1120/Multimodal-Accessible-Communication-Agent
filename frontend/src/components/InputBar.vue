<script setup lang="ts">
import { ref } from 'vue'

import BIcon from '@/components/BIcon.vue'
import { useSessionStore } from '@/stores/session'

const store = useSessionStore()
const text = ref('')

// 医院导诊高频问题快捷按钮
const quickQuestions = [
  '挂号在哪',
  '洗手间在哪',
  '急诊怎么走',
  '骨科在哪',
  '取药处',
  '缴费',
]

async function send(content?: string) {
  const msg = (content ?? text.value).trim()
  if (!msg || !store.sessionId || store.sending) return
  if (content === undefined) text.value = ''
  await store.sendMessage(msg)
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    send()
  }
}
</script>

<template>
  <section class="input-bar" aria-label="输入区">
    <!-- 常用问题快捷按钮 -->
    <div class="quick-questions" v-if="store.sessionId">
      <button
        v-for="q in quickQuestions"
        :key="q"
        class="quick-btn"
        :disabled="store.sending"
        @click="send(q)"
      >
        {{ q }}
      </button>
    </div>

    <div class="field" :class="{ 'is-sending': store.sending }">
      <textarea
        v-model="text"
        :placeholder="store.sessionId ? (store.sending ? '回复中…' : '输入消息，回车发送') : '请先开始会话'"
        rows="1"
        @keydown="onKeydown"
        :disabled="!store.sessionId || store.sending"
      ></textarea>
      <button
        class="send"
        :disabled="!text.trim() || !store.sessionId || store.sending"
        @click="send()"
        aria-label="发送消息"
        title="发送 (Enter)"
      >
        <BIcon v-if="!store.sending" name="send" :size="17" />
        <span v-else class="spinner" aria-label="发送中"></span>
      </button>
    </div>
  </section>
</template>

<style scoped>
.input-bar {
  flex: 1;
  min-width: 0;
  padding: 12px 14px 14px;
  background: var(--color-surface);
}

/* 常用问题快捷按钮 */
.quick-questions {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 10px;
}
.quick-btn {
  padding: 5px 12px;
  border-radius: 16px;
  border: 1px solid var(--color-border);
  background: var(--color-surface-2);
  color: var(--color-text-secondary);
  font-size: 13px;
  cursor: pointer;
  transition: all var(--transition-fast);
  white-space: nowrap;
}
.quick-btn:hover:not(:disabled) {
  border-color: var(--color-primary);
  color: var(--color-primary);
  background: var(--color-primary-soft);
}
.quick-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
[data-mode='elderly'] .quick-btn {
  font-size: 16px;
  padding: 7px 16px;
}
[data-mode='hearing'] .quick-btn {
  border-width: 2px;
}

.field {
  display: flex;
  align-items: flex-end;
  gap: 8px;
  background: var(--color-surface-2);
  border: 1.5px solid var(--color-border);
  border-radius: var(--radius);
  padding: 8px 8px 8px 14px;
  transition: border-color var(--transition-fast), box-shadow var(--transition-fast);
}
.field:focus-within {
  border-color: var(--color-primary);
  box-shadow: 0 0 0 3px var(--color-primary-soft);
  background: var(--color-surface);
}
.field.is-sending {
  opacity: 0.7;
}

textarea {
  flex: 1;
  resize: none;
  border: none;
  background: transparent;
  outline: none;
  color: var(--color-text);
  line-height: 1.5;
  padding: 6px 0;
  max-height: 120px;
}
textarea::placeholder {
  color: var(--color-text-faint);
}
textarea:disabled {
  cursor: not-allowed;
}

.send {
  width: 40px;
  height: 40px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--color-primary-gradient);
  color: #fff;
  border: none;
  box-shadow: var(--shadow-primary);
  flex-shrink: 0;
}
.send:hover:not(:disabled) {
  color: #fff;
  filter: brightness(1.08);
  transform: translateY(-1px);
}
.send:active:not(:disabled) {
  transform: translateY(0);
}
[data-mode='hearing'] .send {
  color: #000;
}

/* 发送中加载动画 */
.spinner {
  width: 18px;
  height: 18px;
  border: 2.5px solid rgba(255, 255, 255, 0.3);
  border-top-color: #fff;
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
}
[data-mode='hearing'] .spinner {
  border-color: rgba(0, 0, 0, 0.3);
  border-top-color: #000;
}
@keyframes spin {
  to { transform: rotate(360deg); }
}
</style>
