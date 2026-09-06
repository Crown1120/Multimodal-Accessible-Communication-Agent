<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'

import BIcon from '@/components/BIcon.vue'
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

function speakerName(m: (typeof store.messages)[number]): string {
  switch (m.role) {
    case 'user':
      return '用户'
    case 'assistant':
      return 'Bridge 助理'
    case 'staff':
      return '工作人员'
    case 'system':
      return '系统'
    default:
      return m.speaker ?? m.role
  }
}

function roleClass(m: (typeof store.messages)[number]): string {
  if (m.role === 'user') return 'user'
  if (m.role === 'assistant') return 'assistant'
  return m.role ?? 'system'
}

function fmtTime(iso?: string): string {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}
</script>

<template>
  <section class="message-list" ref="listRef" aria-label="消息区">
    <div v-if="store.messages.length === 0" class="empty">
      <div class="empty-icon">
        <BIcon name="captions" :size="30" />
      </div>
      <div class="empty-title">开始一段无障碍沟通</div>
      <div class="empty-desc">输入文字、点击说话，或查看实时字幕，Bridge 将协助您完成沟通。</div>
    </div>

    <div
      v-for="m in store.messages"
      :key="m.id"
      class="row"
      :class="roleClass(m)"
    >
      <div class="avatar" v-if="m.role !== 'user'">
        <BIcon :name="m.role === 'assistant' ? 'sparkle' : m.role === 'staff' ? 'user' : 'cpu'" :size="17" />
      </div>

      <div class="bubble-wrap">
        <div class="meta">
          <span class="speaker">{{ speakerName(m) }}</span>
          <span class="time" v-if="fmtTime(m.created_at)">{{ fmtTime(m.created_at) }}</span>
          <span v-if="m.send_status === 'failed'" class="send-status">发送失败</span>
        </div>
        <div class="bubble">
          {{ m.content }}
        </div>
      </div>

      <div class="avatar user" v-if="m.role === 'user'">
        <BIcon name="user" :size="17" />
      </div>
    </div>
  </section>
</template>

<style scoped>
.message-list {
  flex: 1;
  overflow-y: auto;
  padding: 16px 18px;
  display: flex;
  flex-direction: column;
  gap: 16px;
  min-height: 0;
}

/* 空状态 */
.empty {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  color: var(--color-text-muted);
  text-align: center;
  padding: 0 24px;
}
.empty-icon {
  width: 64px;
  height: 64px;
  border-radius: 20px;
  background: var(--color-primary-soft);
  color: var(--color-primary);
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 6px;
}
.empty-title {
  font-size: 1.1em;
  font-weight: 600;
  color: var(--color-text);
}
.empty-desc {
  font-size: 0.88em;
  max-width: 320px;
  line-height: 1.6;
}

/* 消息行 */
.row {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  animation: msgIn 0.28s var(--ease-out);
}
.row.user {
  flex-direction: row-reverse;
}
@keyframes msgIn {
  from {
    opacity: 0;
    transform: translateY(8px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.avatar {
  width: 34px;
  height: 34px;
  border-radius: 12px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--color-surface-2);
  border: 1px solid var(--color-border);
  color: var(--color-primary);
}
.avatar.user {
  background: var(--color-primary-gradient);
  border-color: transparent;
  color: #fff;
}

.bubble-wrap {
  max-width: 76%;
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.row.user .bubble-wrap {
  align-items: flex-end;
}

.meta {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 0.76em;
  color: var(--color-text-faint);
}
.speaker {
  font-weight: 600;
  color: var(--color-text-muted);
}

.bubble {
  padding: 11px 15px;
  border-radius: 4px 16px 16px 16px;
  background: var(--color-surface-2);
  border: 1px solid var(--color-border);
  color: var(--color-text);
  line-height: 1.6;
  word-break: break-word;
  white-space: pre-wrap;
  box-shadow: var(--shadow-xs);
}
.row.assistant .bubble {
  background: var(--color-surface);
}
.row.user .bubble {
  background: var(--color-primary-gradient);
  border-color: transparent;
  color: #fff;
  border-radius: 16px 4px 16px 16px;
  box-shadow: var(--shadow-primary);
}
[data-mode='hearing'] .row.user .bubble,
[data-contrast='on'] .row.user .bubble {
  color: #000;
  font-weight: 500;
}
.row.staff .bubble,
.row.system .bubble {
  background: var(--color-warning-soft);
  border-color: transparent;
}
</style>
