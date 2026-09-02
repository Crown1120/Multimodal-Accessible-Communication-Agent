<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'

import { useSessionStore } from '@/stores/session'

const store = useSessionStore()
const listRef = ref<HTMLElement | null>(null)

watch(
  () => store.messages.length,
  async () => {
    await nextTick()
    listRef.value?.scrollTo({ top: listRef.value.scrollHeight, behavior: 'smooth' })
  },
)
</script>

<template>
  <section class="message-list" ref="listRef" aria-label="消息区">
    <div v-if="store.messages.length === 0" class="empty">
      暂无消息，输入内容开始沟通。
    </div>
    <div
      v-for="m in store.messages"
      :key="m.id"
      class="bubble"
      :class="m.role"
    >
      <div class="speaker">{{ m.role === 'user' ? '用户' : m.role === 'assistant' ? '助理' : m.speaker ?? m.role }}</div>
      <div class="content">{{ m.content }}</div>
    </div>
  </section>
</template>

<style scoped>
.message-list {
  flex: 1;
  overflow-y: auto;
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.empty {
  color: var(--color-text-muted);
  text-align: center;
  margin-top: 24px;
}
.bubble {
  max-width: 80%;
  padding: 10px 14px;
  border-radius: var(--radius);
  background: var(--color-surface);
  border: 1px solid var(--color-border);
}
.bubble.user {
  align-self: flex-end;
  background: var(--color-primary-soft);
  border-color: var(--color-primary);
}
.bubble.assistant {
  align-self: flex-start;
}
.speaker {
  font-size: 0.78em;
  color: var(--color-text-muted);
  margin-bottom: 4px;
}
</style>
