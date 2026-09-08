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
let xingyunWatchdog: ReturnType<typeof window.setTimeout> | null = null

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
      existing.addEventListener(
        'error',
        () => reject(new Error('星云 SDK 脚本加载失败，请检查网络')),
        { once: true },
      )
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

function supportsWebGL2(): boolean {
  const canvas = document.createElement('canvas')
  return Boolean(canvas.getContext('webgl2'))
}

function fallbackFromXingyun(message: string) {
  xingyunError.value = message
  xingyunReady.value = false
  if (xingyunWatchdog !== null) window.clearTimeout(xingyunWatchdog)
  xingyunAvatar?.destroy('xingyun_fallback')
  xingyunAvatar = null
}

function hasRenderedXingyunCanvas(): boolean {
  const container = document.querySelector<HTMLElement>('#xingyun-avatar-container')
  const canvas = container?.querySelector<HTMLCanvasElement>('canvas')
  if (!canvas || canvas.width === 0 || canvas.height === 0) return false

  try {
    const context = canvas.getContext('2d')
    if (context) {
      const pixels = context.getImageData(
        0,
        0,
        Math.min(canvas.width, 8),
        Math.min(canvas.height, 8),
      ).data
      return pixels.some((value) => value !== 0)
    }
  } catch {
    // WebGL canvas cannot be inspected through a 2D context; dimensions are still useful.
  }
  return true
}

async function initXingyun() {
  if (!xingyunConfigured || !xingyunAppId || !xingyunAppSecret) return
  if (!supportsWebGL2()) {
    xingyunError.value = '当前浏览器不支持 WebGL2，已使用降级数字人'
    return
  }
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
        // 并发数已满（Error:7）是服务端配额问题，提示更友好
        if (code === '7' || message.includes('并发') || message.includes('concurrent')) {
          fallbackFromXingyun('数字人服务繁忙，已切换为语音模式（不影响对话）')
        } else {
          fallbackFromXingyun(message || '星云数字人发生错误')
        }
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
    ensureXingyunMuted()
    xingyunWatchdog = window.setTimeout(() => {
      if (!hasRenderedXingyunCanvas()) {
        fallbackFromXingyun('星云数字人未正常渲染，已使用降级数字人')
      }
    }, 5000)
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
  xingyunAvatar.speak(buildSsml(text))
  return true
}

// 构造带语速的 SSML（rate 为百分比，100=原速）
function buildSsml(text: string): string {
  // 纯 SSML（不含 prosody），确保 SDK 正常驱动嘴型与肢体动作
  return `<speak>${escapeSsml(text)}</speak>`
}

// 静音星云 SDK 自身的音频输出（避免与后端 TTS 音频重叠），仅保留嘴型/动作驱动
let xingyunMuteObserver: MutationObserver | null = null
function ensureXingyunMuted() {
  const container = document.getElementById('xingyun-avatar-container')
  if (!container || xingyunMuteObserver) return
  const mute = (el: Element) => {
    if (el instanceof HTMLMediaElement) {
      el.muted = true
      el.volume = 0
    }
  }
  container.querySelectorAll('audio, video').forEach(mute)
  xingyunMuteObserver = new MutationObserver((mutations) => {
    for (const m of mutations) {
      m.addedNodes.forEach((node) => {
        if (node instanceof Element) {
          mute(node)
          node.querySelectorAll('audio, video').forEach(mute)
        }
      })
    }
  })
  xingyunMuteObserver.observe(container, { childList: true, subtree: true })
}

// ---- 播报同步机制 ----
// 后端 TTS 异步化：digital_human.speak（无音频）先到，音频经 1-3s 合成后由
// digital_human.audio_ready 推送。若 speak 一到就调 SDK speak()，SDK 自带字幕
// 会立即开始显示，音频却要等合成完成才播放 → 字幕与音频明显不同步。
// 因此：speak 仅记录状态并启动「音频兜底定时器」，audio_ready 就绪后
// 在同一时刻启动 SDK 播报（字幕+嘴型）与音频播放，保证三者同步。
let speakFallbackTimer: ReturnType<typeof window.setTimeout> | null = null

function clearSpeakFallback() {
  if (speakFallbackTimer !== null) {
    window.clearTimeout(speakFallbackTimer)
    speakFallbackTimer = null
  }
}

// 同时启动：SDK 播报（字幕+嘴型） + 音频播放（或降级浏览器 TTS）
function startSpeechSync() {
  const text = store.speakingText
  if (!text) return
  const speed = store.speakingSpeed || 1.0
  // 先准备音频源（触发解码），让 audio.play() 在 SDK 播报启动后尽快出声
  const hasAudio = Boolean(store.speakingAudioUrl && audioEl.value)
  if (hasAudio) {
    audioEl.value!.src = store.speakingAudioUrl as string
    audioEl.value!.playbackRate = speed
  }
  // 星云可用：SDK 播报（字幕+嘴型）与音频同一时刻启动
  if (xingyunReady.value && xingyunAvatar && !xingyunError.value) {
    try {
      speakWithXingyun(text)
    } catch (e) {
      console.warn('[Xingyun] lip-sync speak failed:', e)
    }
  }
  // 播放后端 TTS 音频
  if (hasAudio) {
    audioEl.value!.play().catch(() => {})
  } else if (!xingyunReady.value) {
    // 星云不可用时兜底浏览器 TTS
    speakWithBrowser(text, speed)
  }
}

// 音频播放结束：停止数字人嘴型动作，确保音画同步
function onAudioEnded() {
  // 尝试停止星云 SDK 播报（如果 SDK 支持 stop 方法）
  if (xingyunAvatar && typeof (xingyunAvatar as Record<string, unknown>).stop === 'function') {
    try {
      (xingyunAvatar as Record<string, () => void>).stop()
    } catch (e) {
      console.warn('[Xingyun] stop speak failed:', e)
    }
  }
  // 浏览器 TTS 兜底：停止 speechSynthesis
  if (window.speechSynthesis.speaking) {
    window.speechSynthesis.cancel()
  }
}

// 监听播报事件：speak 到达时仅记录状态，等待音频就绪后同步启动
watch(
  () => store.speaking,
  (isSpeaking) => {
    if (!isSpeaking) {
      clearSpeakFallback()
      return
    }
    if (!store.speakingText) return
    if (store.speakingAudioUrl) {
      // speak 事件自带音频（同步模式）：立即同步启动
      startSpeechSync()
    } else {
      // 异步模式：等待 audio_ready；4 秒内音频未就绪则兜底，避免播报卡死
      clearSpeakFallback()
      speakFallbackTimer = window.setTimeout(() => {
        if (store.speaking && !store.speakingAudioUrl) {
          startSpeechSync()
          // 星云可用但 TTS 音频未就绪：补一段浏览器语音，避免只动嘴型无声
          if (xingyunReady.value && !xingyunError.value && store.speakingText) {
            speakWithBrowser(store.speakingText, store.speakingSpeed || 1.0)
          }
        }
      }, 4000)
    }
  },
)

// 异步 TTS 音频就绪（digital_human.audio_ready）：字幕、嘴型、音频同一时刻启动
watch(
  () => store.speakingAudioUrl,
  (audioUrl) => {
    if (audioUrl && store.speaking) {
      clearSpeakFallback()
      startSpeechSync()
    }
  },
)

onMounted(async () => {
  // 等待 DOM 渲染完成，确保 v-if 的容器已挂载到 document
  await nextTick()
  // 首屏加速：延迟一帧初始化数字人 SDK，避免阻塞首屏渲染
  // （preload 已在 index.html 预下载 SDK 脚本，此处仅执行初始化）
  setTimeout(() => void initXingyun(), 100)
})

onUnmounted(() => {
  clearSpeakFallback()
  if ('speechSynthesis' in window) {
    window.speechSynthesis.cancel()
  }
  xingyunAvatar?.destroy('component_unmounted')
  xingyunAvatar = null
  if (xingyunWatchdog !== null) window.clearTimeout(xingyunWatchdog)
})

// 顶部状态：说话/思考/加载/待机
const statusMeta = ref<{ icon: string; label: string }>({ icon: 'cpu', label: '待机' })
watch(
  () => [store.speaking, store.agentStatus, xingyunLoading.value, xingyunReady.value, xingyunError.value] as const,
  ([speaking, agentStatus, loading, ready, error]) => {
    if (speaking) statusMeta.value = { icon: 'volume', label: '正在播报…' }
    else if (loading) statusMeta.value = { icon: 'refresh', label: '数字人加载中…' }
    else if (error) statusMeta.value = { icon: 'alert', label: '已降级' }
    else if (agentStatus === 'thinking') statusMeta.value = { icon: 'sparkle', label: '思考中…' }
    else if (agentStatus === 'running') statusMeta.value = { icon: 'cpu', label: '处理中…' }
    else if (agentStatus === 'failed') statusMeta.value = { icon: 'alert', label: '异常' }
    else if (ready) statusMeta.value = { icon: 'check', label: '在线' }
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
      :class="{
        ready: xingyunReady && !xingyunError,
        loading: xingyunLoading,
        hidden: !xingyunConfigured,
        broken: Boolean(xingyunError),
      }"
      aria-label="魔珐星云3D数字人"
    >
      <!-- 顶部信息条（视频通话风格） -->
      <div class="video-top">
        <div class="video-id">
          <span class="live-dot"></span>
          <span class="video-name">Bridge 数字人</span>
          <span v-if="xingyunReady && !xingyunError" class="video-tag">3D 已就绪</span>
          <span v-else-if="xingyunError" class="video-tag warn">已降级</span>
        </div>
        <div class="video-status" :class="store.agentStatus">
          <BIcon :name="statusMeta.icon" :size="13" />
          {{ statusMeta.label }}
        </div>
      </div>

      <!-- 降级提示：友好提示，不暴露技术错误 -->
      <div v-if="xingyunError" class="xingyun-placeholder xingyun-error-overlay">
        <div class="degraded-avatar">
          <div class="degraded-avatar-circle">
            <BIcon name="bridge" :size="36" :stroke-width="1.8" />
          </div>
          <div class="degraded-avatar-text">
            <div class="degraded-title">数字人维护中</div>
            <div class="degraded-sub">文字对话、语音播报、路线指引均正常可用</div>
          </div>
        </div>
      </div>
      <!-- 骨架加载态 / 下载进度 -->
      <div v-if="!xingyunReady && !xingyunError" class="xingyun-placeholder">
        <div class="xingyun-skeleton">
          <div class="skeleton-head"></div>
          <div class="skeleton-body"></div>
        </div>
        <div v-if="xingyunLoading" class="xingyun-progress">
          <div
            class="xingyun-progress-bar"
            :style="{ width: `${xingyunDownloadProgress ?? 0}%` }"
          ></div>
          <span>{{
            xingyunLoading
              ? xingyunDownloadProgress
                ? `下载中 ${xingyunDownloadProgress}%`
                : '初始化数字人…'
              : ''
          }}</span>
        </div>
      </div>

      <!-- 重要信息确认提示（仅关键信息时出现） -->
      <div v-if="store.needRepeat" class="repeat-hint">
        <BIcon name="bell" :size="14" />
        重要信息，请注意确认
      </div>

      <!-- 服务信息：收纳在数字人画面右下方（只展示地点/路线等有用信息） -->
      <div
        v-if="store.widgets.some((w) => w.widget_type !== 'knowledge_source')"
        class="widget-dock"
      >
        <WidgetPanel />
      </div>
    </div>

    <audio ref="audioEl" hidden @ended="onAudioEnded"></audio>
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
  0%,
  100% {
    box-shadow: 0 0 0 0 rgba(229, 72, 77, 0.5);
  }
  50% {
    box-shadow: 0 0 0 7px rgba(229, 72, 77, 0);
  }
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

/* ===== 降级兜底字幕（仅星云不可用时显示，就绪时用 SDK 自带字幕） ===== */
/* ===== 重要信息确认提示（画面底部居中，仅关键信息时出现） ===== */
.repeat-hint {
  position: absolute;
  left: 50%;
  bottom: 58px;
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

/* ===== 数字人画面内字幕 ===== */
.dh-subtitle.hearing {
  font-size: 1.28em;
  font-weight: 600;
  max-width: calc(100% - 380px);
}
.dh-subtitle.elderly {
  font-size: 1.15em;
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
  0% {
    background-position: 200% 0;
  }
  100% {
    background-position: -200% 0;
  }
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
/* 降级态：静态头像 + 友好提示 */
.degraded-avatar {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
}
.degraded-avatar-circle {
  width: 88px;
  height: 88px;
  border-radius: 50%;
  background: linear-gradient(135deg, rgba(59, 130, 246, 0.3), rgba(14, 165, 183, 0.3));
  border: 2px solid rgba(255, 255, 255, 0.15);
  display: flex;
  align-items: center;
  justify-content: center;
  color: #93c5fd;
}
.degraded-avatar-text {
  text-align: center;
}
.degraded-title {
  font-size: 1.05em;
  font-weight: 700;
  color: #e2e8f0;
  margin-bottom: 4px;
}
.degraded-sub {
  font-size: 0.82em;
  color: #94a3b8;
  line-height: 1.5;
}
</style>
