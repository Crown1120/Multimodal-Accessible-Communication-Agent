<script setup lang="ts">
import { onMounted, watch } from 'vue'

import AgentStatus from '@/components/AgentStatus.vue'
import AudioInput from '@/components/AudioInput.vue'
import DigitalHuman from '@/components/DigitalHuman.vue'
import InputBar from '@/components/InputBar.vue'
import MessageList from '@/components/MessageList.vue'
import ModeSwitcher from '@/components/ModeSwitcher.vue'
import PreferencePanel from '@/components/PreferencePanel.vue'
import SubtitleBar from '@/components/SubtitleBar.vue'
import WidgetPanel from '@/components/WidgetPanel.vue'
import { useSessionStore } from '@/stores/session'

const store = useSessionStore()

// 模式变化时同步到根元素（驱动无障碍 CSS 变量）
watch(
  () => store.mode,
  (mode) => {
    document.documentElement.setAttribute('data-mode', mode)
  },
)

onMounted(() => {
  document.documentElement.setAttribute('data-mode', store.mode)
})

async function start() {
  await store.createSession()
}
</script>

<template>
  <div class="workbench">
    <header class="topbar">
      <div class="brand">
        <span class="logo">🌉</span>
        <span class="title">Bridge 无障碍沟通工作台</span>
      </div>
      <div class="status">
        <span class="badge" :class="store.status">
          {{ store.status === 'connected' ? '已连接' : store.status === 'connecting' ? '连接中…' : store.status === 'error' ? '连接异常' : '未连接' }}
        </span>
        <span v-if="store.sessionId" class="session-id">{{ store.sessionId }}</span>
      </div>
      <ModeSwitcher />
      <PreferencePanel />
      <button class="primary" v-if="!store.isConnected" @click="start">开始会话</button>
    </header>

    <main class="body">
      <aside class="left">
        <DigitalHuman />
        <AgentStatus />
      </aside>

      <section class="center">
        <SubtitleBar />
        <MessageList />
        <div class="input-area">
          <InputBar />
          <AudioInput />
        </div>
      </section>

      <aside class="right">
        <WidgetPanel />
      </aside>
    </main>
  </div>
</template>

<style scoped>
.workbench {
  display: flex;
  flex-direction: column;
  height: 100%;
}
.topbar {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 12px 20px;
  background: var(--color-surface);
  border-bottom: 1px solid var(--color-border);
}
.brand {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
}
.logo {
  font-size: 1.4em;
}
.title {
  font-size: 1.05em;
}
.status {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-left: auto;
  margin-right: 8px;
  font-size: 0.85em;
}
.badge {
  padding: 3px 10px;
  border-radius: 999px;
  background: var(--color-bg);
  color: var(--color-text-muted);
}
.badge.connected {
  background: var(--color-primary-soft);
  color: var(--color-primary);
}
.badge.connecting {
  background: #fff4e0;
  color: var(--color-warning);
}
.badge.error {
  background: #fde7e8;
  color: var(--color-danger);
}
.session-id {
  color: var(--color-text-muted);
  font-family: ui-monospace, monospace;
}
.body {
  flex: 1;
  display: grid;
  grid-template-columns: 240px 1fr 320px;
  gap: 1px;
  background: var(--color-border);
  min-height: 0;
}
.left,
.center,
.right {
  background: var(--color-bg);
  display: flex;
  flex-direction: column;
  min-height: 0;
}
.center {
  background: var(--color-surface);
}
.input-area {
  display: flex;
  align-items: stretch;
  gap: 0;
  border-top: 1px solid var(--color-border);
  background: var(--color-surface);
}
.input-area > :first-child {
  flex: 1;
}
</style>
