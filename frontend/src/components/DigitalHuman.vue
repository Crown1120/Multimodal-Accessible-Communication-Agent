<script setup lang="ts">
import { ref, watch, onMounted, onUnmounted, nextTick } from 'vue'

import BIcon from '@/components/BIcon.vue'
import WidgetPanel from '@/components/WidgetPanel.vue'
import { useSessionStore } from '@/stores/session'

const store = useSessionStore()
const audioEl = ref<HTMLAudioElement | null>(null)

// ---- 星云 3D 数字人 SDK（魔珐科技 Xingyun3D）----
// 控制台：https://nebula.xingyun3d.com/  — 需开通「形象授权」和「TTSA 播报」
type XmovAvatarInstance = {
  init: (options?: { onDownloadProgress?: (progress: number) => void }) => Promise<void>
  speak: (ssml: string) => void
  destroy: (reason?: string) => void
}

type XmovAvatarConstructor = new (options: {
  containerId: string
  appId: string
  appSecret: string
  gatewayServer: string
  onMessage: (error: { code?: string; message?: string }) => void
  onStatusChange?: (status: unknown) => void
}) => XmovAvatarInstance

declare global {
  interface Window {
    XmovAvatar?: XmovAvatarConstructor
  }
}

const XINGYUN_SDK_URL = 'https://media.xingyun3d.com/xingyun3d/general/litesdk/xmovAvatar@latest.js'
const XINGYUN_GATEWAY = 'https://nebula-agent.xingyun3d.com/user/v1/ttsa/session'
const xingyunAppId = (import.meta.env.VITE_XINGYUN_APP_ID as string | undefined)?.trim()
const xingyunAppSecret = (import.meta.env.VITE_XINGYUN_APP_SECRET as string | undefined)?.trim()
const xingyunConfigured = Boolean(xingyunAppId && xingyunAppSecret)
const xingyunReady = ref(false)
const xingyunLoading = ref(false)
const xingyunDownloadProgress = ref<number | null>(null)
const xingyunError = ref('')
let xingyunAvatar: XmovAvatarInstance | null = null

// 浏览器原生语音合成（SpeechSynthesis），无需 API Key
function speakWithBrowser(text: string, speed: number) {
  if (!('speechSynthesis' in window) || !text) return
  window.speechSynthesis.cancel()
  const utter = new SpeechSynthesisUtterance(text)
  utter.lang = 'zh-CN'
  utter.rate = speed
  const voices = window.speechSynthesis.getVoices()
  const zhVoice = voices.find((v) => v.lang.startsWith('zh'))
  if (zhVoice) utter.voice = zhVoice
  window.speechSynthesis.speak(utter)
}

function escapeSsml(text: string): string {
  return text.replace(/[&<>"']/g, (char) => {
    const entities: Record<string, string> = {
      '&': '&amp;',
      '<': '&lt;',
      '>': '&gt;',
      '"': '&quot;',
      "'": '&apos;',
    }
    return entities[char]
  })
}

function loadXingyunSdk(): Promise<void> {
  if (window.XmovAvatar) return Promise.resolve()
  return new Promise((resolve, reject) => {
    const existing = document.querySelector<HTMLScriptElement>(`script[src="${XINGYUN_SDK_URL}"]`)
    if (existing) {
      existing.addEventListener('load', () => resolve(), { once: true })
      existing.addEventListener('error', () => reject(new Error('星云 SDK 脚本加载失败，请检查网络')), { once: true })
      return
    }
    const script = document.createElement('script')
    script.src = XINGYUN_SDK_URL
    script.async = true
    script.onload = () => resolve()
    script.onerror = () => reject(new Error('星云 SDK 脚本加载失败，请检查网络或稍后重试'))
    document.head.appendChild(script)
  })
}

async function initXingyun() {
  if (!xingyunConfigured || !xingyunAppId || !xingyunAppSecret) return
  xingyunLoading.value = true
  xingyunError.value = ''
  xingyunDownloadProgress.value = 0
  try {
    await loadXingyunSdk()
    if (!window.XmovAvatar) throw new Error('星云 SDK 加载成功但未暴露 XmovAvatar 构造函数')
    // 注意：SDK 内部使用 querySelector，containerId 需要 # 前缀
    xingyunAvatar = new window.XmovAvatar({
      containerId: '#xingyun-avatar-container',
      appId: xingyunAppId,
      appSecret: xingyunAppSecret,
      gatewayServer: XINGYUN_GATEWAY,
      onMessage: (error) => {
        const code = error.code || ''
        const message = error.message || ''
        xingyunError.value = message || '星云数字人发生错误'
        console.error('[Xingyun] code=%s message=%s', code, message)
      },
      onStatusChange: (status) => {
        console.debug('[Xingyun] status=', status)
      },
    })
    // SDK init：不同版本签名不同，先无参 → 再带参，避免 TypeError
    try {
      await (xingyunAvatar as any).init()
    } catch {
      await (xingyunAvatar as any).init({
        onDownloadProgress: (progress: number) => {
          xingyunDownloadProgress.value = Math.round(progress * 100)
        },
      })
    }
    xingyunReady.value = true
  } catch (error) {
    const msg = error instanceof Error ? error.message : '星云数字人初始化失败'
    xingyunError.value = msg
    console.warn('[Xingyun] fallback to emoji avatar. reason=', error)
  } finally {
    xingyunLoading.value = false
    if (xingyunReady.value) xingyunDownloadProgress.value = null
  }
}

function speakWithXingyun(text: string): boolean {
  if (!xingyunReady.value || !xingyunAvatar || xingyunError.value || !text) return false
  xingyunAvatar.speak(`<speak>${escapeSsml(text)}</speak>`)
  return true
}

// 监听播报事件
watch(
  () => store.speaking,
  (isSpeaking) => {
    if (isSpeaking && store.speakingText) {
      // 优先：后端返回的音频 URL；其次：星云 3D 数字人播报；兜底：浏览器原生 TTS
      if (store.speakingAudioUrl && audioEl.value) {
        audioEl.value.src = store.speakingAudioUrl
        audioEl.value.playbackRate = store.speakingSpeed || 1.0
        audioEl.value.play().catch(() => {})
      } else if (!speakWithXingyun(store.speakingText)) {
        speakWithBrowser(store.speakingText, store.speakingSpeed || 1.0)
      }
    }
  },
)

onMounted(async () => {
  // 等待 DOM 渲染完成，确保 v-if 的容器已挂载到 document
  await nextTick()
  // 额外等一帧，确保 Vue 的 DOM patch 已提交
  await new Promise((r) => setTimeout(r, 50))
  void initXingyun()
})

onUnmounted(() => {
  if ('speechSynthesis' in window) {
    window.speechSynthesis.cancel()
  }
  xingyunAvatar?.destroy('component_unmounted')
  xingyunAvatar = null
})

// 顶部状态：说话/思考/加载/待机
const statusMeta = ref<{ icon: string; label: string }>({ icon: 'cpu', label: '待机' })
watch(
  () => [store.speaking, store.agentStatus, xingyunLoading] as const,
  ([speaking, agentStatus, loading]) => {
    if (speaking) statusMeta.value = { icon: 'volume', label: '正在播报…' }
    else if (loading) statusMeta.value = { icon: 'refresh', label: '数字人加载中…' }
    else if (agentStatus === 'thinking') statusMeta.value = { icon: 'sparkle', label: '思考中…' }
    else if (agentStatus === 'running') statusMeta.value = { icon: 'cpu', label: '处理中…' }
    else if (agentStatus === 'failed') statusMeta.value = { icon: 'alert', label: '异常' }
    else statusMeta.value = { icon: 'cpu', label: '待机' }
  },
  { immediate: true },
)
</script>

<template>
  <section class="digital-human" aria-label="数字人视频通话">
    <!-- 星云 3D 数字人画面：始终渲染到 DOM（v-if 会导致 SDK 构造时找不到元素） -->
    <div
      id="xingyun-avatar-container"
      class="xingyun-avatar"
      :class="{ ready: xingyunReady && !xingyunError, loading: xingyunLoading, hidden: !xingyunConfigured, broken: Boolean(xingyunError) }"
      aria-label="魔珐星云3D数字人"
    >
      <!-- 顶部信息条（视频通话风格） -->
      <div class="video-top">
        <div class="video-id">
          <span class="live-dot"></span>
          <span class="video-name">Bridge 数字人</span>
          <span class="video-tag" v-if="xingyunReady && !xingyunError">3D 已就绪</span>
          <span class="video-tag warn" v-else-if="xingyunError">已降级</span>
        </div>
        <div class="video-status" :class="store.agentStatus">
          <BIcon :name="statusMeta.icon" :size="13" />
          {{ statusMeta.label }}
        </div>
      </div>

      <!-- 错误提示覆盖层 -->
      <div v-if="xingyunError" class="xingyun-placeholder xingyun-error-overlay">
        <div class="xingyun-error">
          <div class="xingyun-error-title">
            <BIcon name="alert" :size="15" />
            3D 数字人暂不可用
          </div>
          <div class="xingyun-error-msg">{{ xingyunError }}</div>
          <div class="xingyun-error-hint">
            请检查：<br />
            ① AppID/AppSecret 是否正确<br />
            ② <a href="https://nebula.xingyun3d.com/" target="_blank" rel="noopener">星云控制台</a> 是否已开通「形象授权」与「TTSA 播报」<br />
            ③ 账户积分是否充足
          </div>
        </div>
      </div>
      <!-- 骨架加载态 / 下载进度 -->
      <div v-if="!xingyunReady && !xingyunError" class="xingyun-placeholder">
        <div class="xingyun-skeleton">
          <div class="skeleton-head"></div>
          <div class="skeleton-body"></div>
        </div>
        <div class="xingyun-progress" v-if="xingyunLoading">
          <div
            class="xingyun-progress-bar"
            :style="{ width: `${xingyunDownloadProgress ?? 0}%` }"
          ></div>
          <span>{{ xingyunLoading ? (xingyunDownloadProgress ? `下载中 ${xingyunDownloadProgress}%` : '初始化数字人…') : '' }}</span>
        </div>
      </div>

      <!-- 重要信息确认提示（仅关键信息时出现） -->
      <div class="repeat-hint" v-if="store.needRepeat">
        <BIcon name="bell" :size="14" />
        重要信息，请注意确认
      </div>

      <!-- 服务信息：收纳在数字人画面右下方（只展示地点/路线等有用信息） -->
      <div class="widget-dock" v-if="store.widgets.some((w) => w.widget_type !== 'knowledge_source')">
        <WidgetPanel />
      </div>

      <!-- 手势提示 -->
      <div class="gesture-label" v-if="store.speaking && store.speakingGesture">
        动作：{{ store.speakingGesture }}
      </div>
    </div>

    <audio ref="audioEl" hidden></audio>
  </section>
</template>

<style scoped>
.digital-human {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  position: relative;
  overflow: hidden;
  background: #060a14;
}

/* 星云 3D 画面：铺满整个舞台（视频通话大画面） */
.xingyun-avatar.hidden {
  display: none !important;
}
.xingyun-avatar {
  flex: 1;
  min-height: 0;
  width: 100%;
  overflow: hidden;
  display: block;
  position: relative;
  background:
    radial-gradient(120% 90% at 50% 0%, rgba(43, 108, 255, 0.22), transparent 55%),
    linear-gradient(180deg, #101a33 0%, #0a0f1f 100%);
}
.xingyun-avatar.ready {
  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.06);
}
.xingyun-avatar.broken {
  background: linear-gradient(180deg, #241318 0%, #160c0c 100%);
}

/* ===== 顶部信息条 ===== */
.video-top {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  z-index: 5;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 12px 16px;
  background: linear-gradient(180deg, rgba(4, 8, 18, 0.72), transparent);
}
.video-id {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #e6edf7;
  font-size: 0.92em;
  font-weight: 600;
}
.live-dot {
  width: 9px;
  height: 9px;
  border-radius: 50%;
  background: var(--color-danger);
  animation: livePulse 1.6s ease-in-out infinite;
  box-shadow: 0 0 0 0 rgba(229, 72, 77, 0.5);
}
@keyframes livePulse {
  0%, 100% { box-shadow: 0 0 0 0 rgba(229, 72, 77, 0.5); }
  50% { box-shadow: 0 0 0 7px rgba(229, 72, 77, 0); }
}
.video-tag {
  font-size: 0.72em;
  font-weight: 600;
  padding: 2px 9px;
  border-radius: var(--radius-pill);
  background: var(--color-success-soft);
  color: var(--color-success);
}
.video-tag.warn {
  background: rgba(245, 158, 11, 0.16);
  color: #fbbf24;
}
.video-status {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 4px 11px;
  border-radius: var(--radius-pill);
  font-size: 0.78em;
  font-weight: 600;
  background: rgba(255, 255, 255, 0.08);
  color: #cbd5e1;
  backdrop-filter: blur(6px);
}
.video-status.thinking {
  color: #7aa2ff;
  background: rgba(59, 130, 246, 0.18);
}
.video-status.running {
  color: #7aa2ff;
  background: rgba(59, 130, 246, 0.18);
}
.video-status.failed {
  color: #fca5a5;
  background: rgba(239, 68, 68, 0.18);
}

/* ===== 重要信息确认提示（画面底部居中，仅关键信息时出现） ===== */
.repeat-hint {
  position: absolute;
  left: 50%;
  bottom: 24px;
  transform: translateX(-50%);
  z-index: 6;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: #ffd43b;
  font-size: 0.86em;
  font-weight: 700;
  padding: 5px 14px;
  background: rgba(0, 0, 0, 0.55);
  border-radius: var(--radius-pill);
  backdrop-filter: blur(4px);
}

/* ===== 服务信息悬浮容器（透明，卡片自带样式，不再套白框） ===== */
.widget-dock {
  position: absolute;
  right: 16px;
  bottom: 18px;
  z-index: 7;
  width: 330px;
  max-width: 42%;
  max-height: calc(100% - 48px);
  display: flex;
  flex-direction: column;
}
.widget-dock :deep(.widget-panel) {
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-height: 0;
  max-height: inherit;
  overflow-y: auto;
}

@media (max-width: 820px) {
  .widget-dock {
    width: 280px;
    max-width: 50%;
  }
}
@media (max-width: 640px) {
  .widget-dock {
    width: 220px;
    max-width: 60%;
  }
}

.repeat-hint {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  align-self: center;
  color: #ffd43b;
  font-size: 0.86em;
  font-weight: 700;
  padding: 5px 14px;
  background: rgba(0, 0, 0, 0.55);
  border-radius: var(--radius-pill);
  backdrop-filter: blur(4px);
}

.gesture-label {
  position: absolute;
  right: 16px;
  bottom: 14px;
  z-index: 4;
  color: rgba(255, 255, 255, 0.6);
  font-size: 0.8em;
  font-weight: 600;
}

/* ===== 占位/加载/错误 ===== */
.xingyun-placeholder {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 14px;
  color: #e2e8f0;
  z-index: 2;
}
.xingyun-error-overlay {
  z-index: 10;
}
.xingyun-skeleton {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
}
.skeleton-head {
  width: 72px;
  height: 72px;
  border-radius: 50%;
  background: linear-gradient(
    100deg,
    rgba(255, 255, 255, 0.08) 30%,
    rgba(255, 255, 255, 0.2) 50%,
    rgba(255, 255, 255, 0.08) 70%
  );
  background-size: 200% 100%;
  animation: shimmer 1.8s ease-in-out infinite;
}
.skeleton-body {
  width: 128px;
  height: 200px;
  border-radius: 64px 64px 22px 22px;
  background: linear-gradient(
    100deg,
    rgba(255, 255, 255, 0.08) 30%,
    rgba(255, 255, 255, 0.2) 50%,
    rgba(255, 255, 255, 0.08) 70%
  );
  background-size: 200% 100%;
  animation: shimmer 1.8s ease-in-out infinite;
}
@keyframes shimmer {
  0% { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}
.xingyun-progress {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  width: 100%;
  font-size: 12px;
  color: #94a3b8;
}
.xingyun-progress-bar {
  height: 5px;
  width: 80%;
  border-radius: 999px;
  background: var(--color-primary-gradient);
  transition: width 0.3s ease;
}
.xingyun-error {
  text-align: left;
  font-size: 12px;
  line-height: 1.5;
  width: 100%;
  max-width: 460px;
}
.xingyun-error-title {
  display: flex;
  align-items: center;
  gap: 5px;
  font-weight: 700;
  font-size: 13px;
  color: #fcd34d;
  margin-bottom: 4px;
}
.xingyun-error-msg {
  color: #fecaca;
  word-break: break-all;
  margin-bottom: 6px;
}
.xingyun-error-hint {
  color: #cbd5e1;
  margin-top: 4px;
}
.xingyun-error-hint a {
  color: #7aa2ff;
  text-decoration: underline;
}
</style>
