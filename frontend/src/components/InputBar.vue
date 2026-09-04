<script setup lang="ts">
import { ref } from 'vue'

import BIcon from '@/components/BIcon.vue'
import { useSessionStore } from '@/stores/session'

const store = useSessionStore()
const text = ref('')

async function send() {
  const content = text.value.trim()
  if (!content || !store.sessionId) return
  text.value = ''
  await store.sendMessage(content)
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
    <div class="field">
      <textarea
        v-model="text"
        :placeholder="store.sessionId ? '输入消息，回车发送' : '请先开始会话'"
        rows="1"
        @keydown="onKeydown"
        :disabled="!store.sessionId"
      ></textarea>
      <button
        class="send"
        :disabled="!text.trim() || !store.sessionId"
        @click="send"
        aria-label="发送消息"
        title="发送 (Enter)"
      >
        <BIcon name="send" :size="17" />
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
</style>
