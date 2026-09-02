<script setup lang="ts">
import { ref } from 'vue'

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
    <textarea
      v-model="text"
      :placeholder="store.sessionId ? '输入消息，回车发送' : '请先开始会话'"
      rows="2"
      @keydown="onKeydown"
      :disabled="!store.sessionId"
    ></textarea>
    <button class="primary" :disabled="!text.trim() || !store.sessionId" @click="send">
      发送
    </button>
  </section>
</template>

<style scoped>
.input-bar {
  display: flex;
  gap: 8px;
  padding: 12px;
  background: var(--color-surface);
}
textarea {
  flex: 1;
  resize: none;
  padding: 10px 12px;
  border: 1px solid var(--color-border);
  border-radius: 8px;
  background: var(--color-bg);
  color: var(--color-text);
}
textarea:focus {
  outline: none;
  border-color: var(--color-primary);
}
</style>
