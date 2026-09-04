<script setup lang="ts">
import { computed, onMounted, watch } from 'vue'

import AudioInput from '@/components/AudioInput.vue'
import BIcon from '@/components/BIcon.vue'
import DigitalHuman from '@/components/DigitalHuman.vue'
import InputBar from '@/components/InputBar.vue'
import ModeSwitcher from '@/components/ModeSwitcher.vue'
import PreferencePanel from '@/components/PreferencePanel.vue'
import { useSessionStore } from '@/stores/session'

const store = useSessionStore()

// 模式变化时同步到根元素（驱动无障碍 CSS 变量）
watch(
  () => store.mode,
  (mode) => {
    document.documentElement.setAttribute('data-mode', mode)
  },
)

// 自动创建会话：页面加载即连接，无需用户点击
async function autoConnect() {
  try {
    await store.createSession()
  } catch (e) {
    console.error('自动连接失败，将在 3 秒后重试', e)
    // 失败后自动重试（最多 3 次）
    for (let attempt = 0; attempt < 3; attempt++) {
      await new Promise((r) => setTimeout(r, 3000))
      try {
        await store.createSession()
        return
      } catch {
        console.warn(`自动连接重试 ${attempt + 1}/3 失败`)
      }
    }
    // 3 次都失败，状态保持 error，用户可手动点重新连接
  }
}

onMounted(() => {
  document.documentElement.setAttribute('data-mode', store.mode)
  // 页面加载后自动创建会话
  autoConnect()
})

// 手动重新连接（自动连接失败时可用）
async function reconnect() {
  await autoConnect()
}

const sceneInfo = computed<{ label: string; icon: 'hospital' | 'government' }>(() =>
  store.scene === 'government'
    ? { label: '政务大厅', icon: 'government' }
    : { label: '医院场景', icon: 'hospital' },
)

const statusInfo = computed(() => {
  switch (store.status) {
    case 'connected':
      return { label: '已连接', icon: 'check' as const, cls: 'connected' }
    case 'connecting':
      return { label: '连接中…', icon: 'refresh' as const, cls: 'connecting' }
    case 'error':
      return { label: '连接异常', icon: 'alert' as const, cls: 'error' }
    default:
      return { label: '未连接', icon: 'wifi' as const, cls: 'offline' }
  }
})
</script>

<template>
  <div class="workbench">
    <header class="topbar">
      <div class="brand">
        <div class="brand-logo">
          <BIcon name="bridge" :size="22" :stroke-width="2.1" />
        </div>
        <div class="brand-text">
          <div class="brand-title">Bridge 无障碍沟通工作台</div>
          <div class="brand-sub">多模态 · 实时沟通 · 无障碍服务</div>
        </div>
        <span class="scene-chip">
          <BIcon :name="sceneInfo.icon" :size="15" />
          {{ sceneInfo.label }}
        </span>
      </div>

      <div class="topbar-right">
        <div class="conn" :class="statusInfo.cls" role="status">
          <BIcon :name="statusInfo.icon" :size="15" />
          <span>{{ statusInfo.label }}</span>
        </div>
        <span v-if="store.sessionId" class="session-id" :title="store.sessionId">
          {{ store.sessionId.slice(0, 8) }}
        </span>
        <ModeSwitcher />
        <PreferencePanel />
        <button v-if="store.status === 'error'" class="primary start-btn" @click="reconnect">
          重新连接
        </button>
      </div>
    </header>

    <main class="body">
      <!-- 视频通话主画面：数字人居中，服务信息也收纳在数字人框内 -->
      <section class="stage" aria-label="视频通话画面">
        <DigitalHuman />
        <div class="control-bar">
          <InputBar />
          <AudioInput />
        </div>
      </section>
    </main>
  </div>
</template>

<style scoped>
.workbench {
  display: flex;
  flex-direction: column;
  height: 100%;
  background:
    radial-gradient(900px 400px at 12% -8%, rgba(43, 108, 255, 0.08), transparent 60%),
    radial-gradient(900px 400px at 92% -6%, rgba(14, 165, 183, 0.1), transparent 60%),
    var(--color-bg);
}

/* ===== 顶栏 ===== */
.topbar {
  display: flex;
  align-items: center;
  gap: 14px;
  height: var(--topbar-height);
  padding: 0 20px;
  background: color-mix(in srgb, var(--color-surface) 82%, transparent);
  backdrop-filter: blur(14px);
  -webkit-backdrop-filter: blur(14px);
  border-bottom: 1px solid var(--color-border);
  position: relative;
  z-index: 20;
}

.brand {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}

.brand-logo {
  width: 40px;
  height: 40px;
  border-radius: 12px;
  background: var(--color-primary-gradient);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: var(--shadow-primary);
  flex-shrink: 0;
}

.brand-text {
  display: flex;
  flex-direction: column;
  line-height: 1.25;
  white-space: nowrap;
}

.brand-title {
  font-weight: 700;
  font-size: 1.02em;
  letter-spacing: 0.2px;
}

.brand-sub {
  font-size: 0.74em;
  color: var(--color-text-muted);
}

.scene-chip {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 4px 10px;
  border-radius: var(--radius-pill);
  background: var(--color-primary-soft);
  color: var(--color-primary);
  font-size: 0.82em;
  font-weight: 600;
  white-space: nowrap;
  margin-left: 4px;
}

.topbar-right {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 12px;
}

.conn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 5px 12px;
  border-radius: var(--radius-pill);
  font-size: 0.85em;
  font-weight: 600;
  border: 1px solid var(--color-border);
  background: var(--color-surface);
  color: var(--color-text-muted);
}
.conn.connected {
  color: var(--color-success);
  background: var(--color-success-soft);
  border-color: transparent;
}
.conn.connecting {
  color: var(--color-warning);
  background: var(--color-warning-soft);
  border-color: transparent;
}
.conn.connecting .b-icon {
  animation: spin 1s linear infinite;
}
.conn.error {
  color: var(--color-danger);
  background: var(--color-danger-soft);
  border-color: transparent;
}

.session-id {
  color: var(--color-text-faint);
  font-family: var(--font-mono);
  font-size: 0.78em;
  padding: 3px 8px;
  border: 1px dashed var(--color-border-strong);
  border-radius: 6px;
}

.start-btn {
  padding: 8px 18px;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

/* ===== 主体：全屏视频通话画面 ===== */
.body {
  flex: 1;
  display: flex;
  min-height: 0;
  padding: 14px 18px 18px;
}

.stage {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
  border-radius: var(--radius-lg);
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  box-shadow: var(--shadow-sm);
  overflow: hidden;
  position: relative;
}

/* 视频通话控制条：输入 + 麦克风 */
.control-bar {
  display: flex;
  align-items: stretch;
  gap: 0;
  border-top: 1px solid var(--color-border);
  background: var(--color-surface);
  flex-shrink: 0;
}
.control-bar > :deep(.input-bar) {
  border-right: 1px solid var(--color-border);
}
</style>
