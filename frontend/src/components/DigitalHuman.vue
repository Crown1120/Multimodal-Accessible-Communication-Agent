<script setup lang="ts">
import { ref, watch, onMounted, onUnmounted, nextTick } from 'vue'

import BIcon, { type IconName } from '@/components/BIcon.vue'
import { api } from '@/services/api'
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
const xingyunReady = ref(false)
const xingyunLoading = ref(false)
const xingyunDownloadProgress = ref<number | null>(null)
const xingyunError = ref('')
let xingyunAvatar: XmovAvatarInstance | null = null
let xingyunWatchdog: number | null = null
let initTimer: number | null = null
let disposed = false

/**
 * 解析星云凭据。
 *
 * 只从后端 `/api/config/public` 取运行时配置——凭据不内联进静态产物，
 * 运营侧不重新构建前端即可轮换密钥。
 *
 * 注意：星云 SDK 的设计要求 appSecret 出现在浏览器中（见官方快速开始文档），
 * 因此该密钥对终端用户本质上是公开的，必须使用域名白名单 + 配额限制的专用密钥。
 */
let resolvedCredentials: { appId: string; appSecret: string } | null = null
let credentialsResolved = false

async function resolveCredentials(): Promise<{ appId: string; appSecret: string } | null> {
  if (credentialsResolved) return resolvedCredentials
  try {
    const cfg = await api.getPublicConfig()
    if (cfg.xingyun_app_id && cfg.xingyun_app_secret) {
      resolvedCredentials = { appId: cfg.xingyun_app_id, appSecret: cfg.xingyun_app_secret }
    }
    credentialsResolved = true
  } catch {
    // 网络失败不缓存结果，下一次挂载仍可恢复数字人。
  }
  return resolvedCredentials
}

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
  // 浏览器语音播报结束：复位播报状态，避免「正在播报」一直显示
  utter.onend = () => store.stopSpeaking()
  utter.onerror = () => store.stopSpeaking()
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
  const credentials = await resolveCredentials()
  if (disposed || !credentials) return
  if (!supportsWebGL2()) {
    xingyunError.value = '当前浏览器不支持 WebGL2，已使用降级数字人'
    return
  }
  xingyunLoading.value = true
  xingyunError.value = ''
  xingyunDownloadProgress.value = 0
  try {
    await loadXingyunSdk()
    if (disposed) return
    if (!window.XmovAvatar) throw new Error('星云 SDK 加载成功但未暴露 XmovAvatar 构造函数')
    // 注意：SDK 内部使用 querySelector，containerId 需要 # 前缀
    xingyunAvatar = new window.XmovAvatar({
      containerId: '#xingyun-avatar-container',
      appId: credentials.appId,
      appSecret: credentials.appSecret,
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
        if (import.meta.env.DEV) console.warn('[Xingyun] status=', status)
      },
    })
    if (disposed) {
      xingyunAvatar.destroy('component_unmounted')
      xingyunAvatar = null
      return
    }
    // SDK init：不同版本签名不同，先无参 → 再带参，避免 TypeError
    const avatarWithInit = xingyunAvatar as unknown as {
      init: (options?: { onDownloadProgress?: (progress: number) => void }) => Promise<void>
    }
    try {
      await avatarWithInit.init()
    } catch {
      await avatarWithInit.init({
        onDownloadProgress: (progress: number) => {
          xingyunDownloadProgress.value = Math.round(progress * 100)
        },
      })
    }
    if (disposed) {
      xingyunAvatar.destroy('component_unmounted')
      xingyunAvatar = null
      return
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
  try {
    xingyunAvatar.speak(buildSsml(text))
    return true
  } catch (e) {
    console.warn('[Xingyun] speak failed:', e)
    return false
  }
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
let speakFallbackTimer: number | null = null
// 播报同步防抖：同一轮播报可能同时触发多个 watch（speaking / speakingAudioUrl /
// speakingRunId），导致 startSpeechSync 被重复调用、SDK speak 连续执行两次
// （第二次会打断第一次，造成嘴型/字幕不稳定甚至卡住）。加 300ms 窗口防抖。
let speechSyncPending = false

function clearSpeakFallback() {
  if (speakFallbackTimer !== null) {
    window.clearTimeout(speakFallbackTimer)
    speakFallbackTimer = null
  }
}

// 同时启动：SDK 播报（字幕+嘴型） + 音频播放（或降级浏览器 TTS）
function startSpeechSync() {
  if (speechSyncPending) return
  speechSyncPending = true
  window.setTimeout(() => {
    speechSyncPending = false
  }, 300)
  const text = store.speakingText
  if (!text) return
  const speed = store.speakingSpeed || 1.0
  // 记录本轮播报 run_id：防止旧音频的 ended 事件打断新一轮 SDK 播报
  if (audioEl.value) {
    audioEl.value.dataset.runId = store.speakingRunId ?? ''
  }
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
    audioEl.value!.play().catch((err) => {
      // 浏览器自动播放策略会阻止未交互页面播放音频；此时不能静默失败，
      // 否则用户听不到任何声音却看不出原因。降级到浏览器语音并提示一次。
      console.warn('[Audio] 播放被阻止，降级为浏览器语音：', err)
      if (store.speakingText) speakWithBrowser(store.speakingText, speed)
    })
  } else if (!xingyunReady.value) {
    // 星云不可用时兜底浏览器 TTS
    speakWithBrowser(text, speed)
  }
}

// 音频播放结束：停止数字人嘴型动作，确保音画同步
function onAudioEnded() {
  // 旧音频的 ended（已播放到末尾但期间新一轮播报已替换音频源）：
  // 直接忽略，避免打断当前轮次的 SDK 字幕/嘴型
  const currentRunId = store.speakingRunId ?? ''
  if (audioEl.value && audioEl.value.dataset.runId !== currentRunId) {
    return
  }
  // 不主动调用 SDK stop()：让星云 SDK 的 TTSA 播报自然结束（SDK 会自动回到空闲状态）。
  // 音频播完立即 stop() 会触发 SDK 日志 "10006 ttsa主动关闭 / client quit"，
  // 连续对话时频繁开关 TTSA 会话会导致后续 speak 被拒绝，数字人嘴型/字幕不再更新（卡住）。
  // 仅停止浏览器 TTS 兜底（SpeechSynthesis 没有自然结束回调链）
  if (window.speechSynthesis.speaking) {
    window.speechSynthesis.cancel()
  }
  // 复位播报状态：音频播完即恢复待机，防止「正在播报」永久显示
  store.stopSpeaking()
}

// 音频加载/播放失败（404、解码失败、被阻止等）：
// ended 不会触发，若不处理播报状态将卡 60 秒才被兜底定时器复位。
// 处理：停止 SDK 播报（避免视觉与声音双轨冲突）→ 降级浏览器语音（其 onend 会复位状态）。
function onAudioError() {
  const currentRunId = store.speakingRunId ?? ''
  if (audioEl.value && audioEl.value.dataset.runId !== currentRunId) {
    return
  }
  console.warn('[Audio] 音频加载/播放失败，降级为浏览器语音')
  const stoppable = xingyunAvatar as unknown as { stop?: () => void } | null
  if (stoppable && typeof stoppable.stop === 'function') {
    try {
      stoppable.stop()
    } catch (e) {
      console.warn('[Xingyun] stop on audio error failed:', e)
    }
  }
  if (window.speechSynthesis.speaking) {
    window.speechSynthesis.cancel()
  }
  if (store.speakingText) {
    speakWithBrowser(store.speakingText, store.speakingSpeed || 1.0)
  } else {
    store.stopSpeaking()
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

// 新一轮 SSE 播报（run_id 变化）：即使 speaking 已是 true（无 false→true 边沿，
// 例如连续消息或上一轮未完全结束）也重置并重新同步启动，
// 修复数字人卡住、字幕不更新的问题。本地播报（run_id=null）由 speakTick watch 驱动。
watch(
  () => store.speakingRunId,
  (runId) => {
    if (!runId || !store.speaking || !store.speakingText) return
    clearSpeakFallback()
    if (store.speakingAudioUrl) {
      startSpeechSync()
    } else {
      // 异步模式：等 audio_ready；4 秒内音频未就绪则兜底，避免播报卡死
      speakFallbackTimer = window.setTimeout(() => {
        if (store.speaking && !store.speakingAudioUrl) {
          startSpeechSync()
          if (xingyunReady.value && !xingyunError.value && store.speakingText) {
            speakWithBrowser(store.speakingText, store.speakingSpeed || 1.0)
          }
        }
      }, 4000)
    }
  },
)

// 本地播报请求（store.speak：重复一遍 / 路线语音导航）：无需等 TTS 音频，立即播报
watch(
  () => store.speakTick,
  () => {
    if (!store.speaking) return
    clearSpeakFallback()
    startSpeechSync()
  },
)

// 主动打断（发送新消息）：强制停止 SDK 正在进行的 TTSA 会话，
// 避免新旧 speak 在 SDK 内叠加/冲突导致数字人嘴型、字幕卡住。
// 与音频自然结束（onAudioEnded）不同：自然结束让 SDK 播完，这里必须立即停。
watch(
  () => store.sdkInterruptTick,
  () => {
    const stoppable = xingyunAvatar as unknown as { stop?: () => void } | null
    if (stoppable && typeof stoppable.stop === 'function') {
      try {
        stoppable.stop()
      } catch (e) {
        console.warn('[Xingyun] interrupt stop failed:', e)
      }
    }
    if (window.speechSynthesis.speaking) {
      window.speechSynthesis.cancel()
    }
  },
)

onMounted(async () => {
  disposed = false
  // 等待 DOM 渲染完成，确保 v-if 的容器已挂载到 document
  await nextTick()
  // 首屏加速：延迟一帧初始化数字人 SDK，避免阻塞首屏渲染
  // （SDK 脚本在 initXingyun 内按需动态注入，未配置数字人时不下载数 MB 脚本）
  initTimer = window.setTimeout(() => {
    initTimer = null
    void initXingyun()
  }, 100)
})

onUnmounted(() => {
  disposed = true
  if (initTimer !== null) {
    window.clearTimeout(initTimer)
    initTimer = null
  }
  clearSpeakFallback()
  // 释放 MutationObserver，避免组件卸载后回调仍持有 DOM 引用
  xingyunMuteObserver?.disconnect()
  xingyunMuteObserver = null
  // 停止并释放音频，避免卸载后继续出声
  if (audioEl.value) {
    audioEl.value.pause()
    audioEl.value.removeAttribute('src')
    audioEl.value.load()
  }
  if ('speechSynthesis' in window) {
    window.speechSynthesis.cancel()
  }
  xingyunAvatar?.destroy('component_unmounted')
  xingyunAvatar = null
  if (xingyunWatchdog !== null) window.clearTimeout(xingyunWatchdog)
})

// 顶部状态：说话/思考/加载/待机
const statusMeta = ref<{ icon: IconName; label: string }>({ icon: 'cpu', label: '待机' })
watch(
  () =>
    [
      store.speaking,
      store.agentStatus,
      xingyunLoading.value,
      xingyunReady.value,
      xingyunError.value,
    ] as const,
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
        hidden: !xingyunReady && !xingyunLoading,
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
    </div>

    <audio ref="audioEl" hidden @ended="onAudioEnded" @error="onAudioError"></audio>
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
