<script setup lang="ts">
import { computed, ref, watch, onUnmounted } from 'vue'

import { useSessionStore } from '@/stores/session'

const store = useSessionStore()
const audioEl = ref<HTMLAudioElement | null>(null)

// 手势对应的 emoji 与描述
const GESTURE_EMOJI: Record<string, { icon: string; label: string }> = {
  wave: { icon: '👋', label: '挥手' },
  gesture_open: { icon: '🤲', label: '手势引导' },
  point_right: { icon: '👉', label: '指向右侧' },
  point_left: { icon: '👈', label: '指向左侧' },
  point_up: { icon: '☝️', label: '指向上方' },
  point_down: { icon: '👇', label: '指向下方' },
  bow: { icon: '🙇', label: '鞠躬' },
  think: { icon: '🤔', label: '思考' },
  raise_hand: { icon: '✋', label: '举手提示' },
  idle: { icon: '', label: '' },
}

// 表情对应的 emoji
const EXPRESSION_EMOJI: Record<string, string> = {
  smile: '🙂',
  happy: '😄',
  sad: '😢',
  apologetic: '😔',
  serious: '😐',
  neutral: '🧑‍💼',
}

const gestureInfo = computed(() => GESTURE_EMOJI[store.speakingGesture] ?? GESTURE_EMOJI.idle)
const faceEmoji = computed(() => EXPRESSION_EMOJI[store.speakingExpression] ?? EXPRESSION_EMOJI.neutral)

// 浏览器原生语音合成（SpeechSynthesis），无需 API Key
function speakWithBrowser(text: string, speed: number) {
  if (!('speechSynthesis' in window) || !text) return
  // 取消之前的播报
  window.speechSynthesis.cancel()
  const utter = new SpeechSynthesisUtterance(text)
  utter.lang = 'zh-CN'
  utter.rate = speed
  // 尝试使用中文语音
  const voices = window.speechSynthesis.getVoices()
  const zhVoice = voices.find((v) => v.lang.startsWith('zh'))
  if (zhVoice) utter.voice = zhVoice
  window.speechSynthesis.speak(utter)
}

// 监听播报事件
watch(
  () => store.speaking,
  (isSpeaking) => {
    if (isSpeaking && store.speakingText) {
      // 优先使用后端音频 URL；无 URL 时用浏览器语音合成
      if (store.speakingAudioUrl && audioEl.value) {
        audioEl.value.src = store.speakingAudioUrl
        audioEl.value.playbackRate = store.speakingSpeed || 1.0
        audioEl.value.play().catch(() => {})
      } else {
        // 使用浏览器原生 TTS（不需要 API Key）
        speakWithBrowser(store.speakingText, store.speakingSpeed || 1.0)
      }
    }
  },
)

// 组件卸载时停止播报
onUnmounted(() => {
  if ('speechSynthesis' in window) {
    window.speechSynthesis.cancel()
  }
})
</script>

<template>
  <section class="digital-human" aria-label="数字人">
    <div
      class="avatar"
      :class="[store.agentStatus, store.speakingExpression, { speaking: store.speaking }]"
    >
      <span class="face">{{ faceEmoji }}</span>
      <span class="gesture" v-if="gestureInfo.icon">{{ gestureInfo.icon }}</span>
    </div>
    <div class="state">
      <span v-if="store.speaking">正在播报…</span>
      <span v-else-if="store.agentStatus === 'idle'">待机</span>
      <span v-else-if="store.agentStatus === 'thinking'">思考中…</span>
      <span v-else-if="store.agentStatus === 'running'">处理中…</span>
      <span v-else-if="store.agentStatus === 'failed'">异常</span>
    </div>
    <div class="gesture-label" v-if="store.speaking && gestureInfo.label">
      动作：{{ gestureInfo.label }}
    </div>
    <div class="repeat-hint" v-if="store.needRepeat" role="status">
      🔔 重要信息，请注意确认
    </div>
    <div class="bubble" v-if="store.speaking && store.speakingText">
      {{ store.speakingText }}
    </div>
    <audio ref="audioEl" hidden></audio>
  </section>
</template>

<style scoped>
.digital-human {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  padding: 16px;
}
.avatar {
  width: 132px;
  height: 132px;
  border-radius: 50%;
  background: var(--color-primary-soft);
  display: grid;
  place-items: center;
  font-size: 64px;
  border: 3px solid var(--color-border);
  transition: all var(--transition-fast);
  position: relative;
}
.avatar.thinking,
.avatar.running {
  border-color: var(--color-primary);
  animation: pulse 1.4s ease-in-out infinite;
}
.avatar.speaking {
  border-color: var(--color-accent);
  animation: speakPulse 0.9s ease-in-out infinite;
}
.avatar.sad,
.avatar.apologetic {
  border-color: var(--color-danger);
}
.avatar.failed {
  border-color: var(--color-danger);
}
.gesture {
  position: absolute;
  bottom: -8px;
  right: -8px;
  font-size: 32px;
  animation: gestureIn 0.3s ease;
}
@keyframes gestureIn {
  from {
    opacity: 0;
    transform: scale(0.5);
  }
  to {
    opacity: 1;
    transform: scale(1);
  }
}
@keyframes pulse {
  0%,
  100% {
    transform: scale(1);
  }
  50% {
    transform: scale(1.04);
  }
}
@keyframes speakPulse {
  0%,
  100% {
    box-shadow: 0 0 0 0 rgba(20, 184, 166, 0.4);
  }
  50% {
    box-shadow: 0 0 0 10px rgba(20, 184, 166, 0);
  }
}
.state {
  color: var(--color-text-muted);
  font-size: 0.9em;
}
.gesture-label {
  color: var(--color-primary);
  font-size: 0.8em;
  font-weight: 600;
}
.repeat-hint {
  color: var(--color-warning);
  font-size: 0.85em;
  font-weight: 600;
  padding: 4px 8px;
  background: rgba(245, 166, 35, 0.12);
  border-radius: 6px;
}
.bubble {
  margin-top: 4px;
  padding: 8px 12px;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
  font-size: 0.9em;
  color: var(--color-text);
  max-width: 220px;
  text-align: center;
}
</style>
