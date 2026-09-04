<script setup lang="ts">
import { ref } from 'vue'

import BIcon from '@/components/BIcon.vue'
import { useSessionStore } from '@/stores/session'

const store = useSessionStore()

const error = ref<string>('')
const interimText = ref<string>('')

// ---- 录音上传 + 后端 ASR（MediaRecorder）----
const mediaRecorder = ref<MediaRecorder | null>(null)
const chunks = ref<Blob[]>([])

function pickMime(): string {
  const candidates = [
    'audio/webm;codecs=opus',
    'audio/webm',
    'audio/ogg;codecs=opus',
    'audio/mp4',
  ]
  for (const m of candidates) {
    if (MediaRecorder.isTypeSupported(m)) return m
  }
  return ''
}

async function startRecording() {
  if (!store.sessionId || store.recording) return
  error.value = ''
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    const mime = pickMime()
    const recorder = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined)
    chunks.value = []

    recorder.ondataavailable = (e) => {
      if (e.data.size > 0) chunks.value.push(e.data)
    }

    recorder.onstop = async () => {
      const audioBlob = new Blob(chunks.value, { type: mime || 'audio/webm' })
      stream.getTracks().forEach((t) => t.stop())
      await store.uploadAudio(audioBlob)
    }

    recorder.start()
    mediaRecorder.value = recorder
    store.recording = true
  } catch {
    error.value = '无法访问麦克风，请检查浏览器权限或使用文字输入'
    store.recording = false
  }
}

function stopRecording() {
  if (mediaRecorder.value && mediaRecorder.value.state === 'recording') {
    mediaRecorder.value.stop()
  }
  store.recording = false
}

// 统一入口：直接使用录音上传 + 后端 Vosk 离线识别
// （Web Speech API 需要连接 Google 服务器，国内不可用）
function start() {
  startRecording()
}

function stop() {
  stopRecording()
}

const waveBars = [0.9, 0.55, 1, 0.7, 0.45, 0.85, 0.6, 0.95, 0.5, 0.75]
</script>

<template>
  <section class="audio-input" aria-label="语音输入">
    <button
      class="mic"
      :class="{ recording: store.recording }"
      :disabled="!store.sessionId"
      @click="store.recording ? stop() : start()"
      :aria-pressed="store.recording"
      :title="store.recording ? '停止录音' : '开始说话'"
    >
      <span class="wave" v-if="store.recording" aria-hidden="true">
        <i v-for="(h, i) in waveBars" :key="i" :style="{ height: `${h * 100}%` }"></i>
      </span>
      <span class="icon" v-else>
        <BIcon name="mic" :size="20" />
      </span>
      <span class="label">{{ store.recording ? '停止' : '说话' }}</span>
    </button>

    <div class="hint" v-if="store.recording && interimText">{{ interimText }}</div>
    <div class="hint" v-else-if="store.recording">正在聆听…</div>
    <div class="error" v-if="error" role="alert">{{ error }}</div>
  </section>
</template>

<style scoped>
.audio-input {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 12px 16px 14px;
  min-width: 132px;
}

.mic {
  display: flex;
  align-items: center;
  gap: 8px;
  border-radius: var(--radius-pill);
  padding: 9px 20px;
  font-size: 1em;
  font-weight: 600;
  border: 1.5px solid var(--color-border);
  background: var(--color-surface);
  color: var(--color-primary);
  box-shadow: var(--shadow-xs);
}
.mic:hover:not(:disabled) {
  border-color: var(--color-primary);
  background: var(--color-primary-soft);
}
.mic.recording {
  background: var(--color-danger);
  color: #fff;
  border-color: var(--color-danger);
  animation: recordPulse 1.4s ease-in-out infinite;
}
@keyframes recordPulse {
  0%,
  100% {
    box-shadow: 0 0 0 0 rgba(229, 72, 77, 0.45);
  }
  50% {
    box-shadow: 0 0 0 10px rgba(229, 72, 77, 0);
  }
}

/* 录音波形 */
.wave {
  display: flex;
  align-items: center;
  gap: 3px;
  height: 20px;
}
.wave i {
  display: block;
  width: 3px;
  border-radius: 2px;
  background: currentColor;
  animation: wave 0.9s ease-in-out infinite;
}
.wave i:nth-child(2n) {
  animation-delay: 0.15s;
}
.wave i:nth-child(3n) {
  animation-delay: 0.3s;
}
@keyframes wave {
  0%,
  100% {
    transform: scaleY(0.35);
  }
  50% {
    transform: scaleY(1);
  }
}

.hint {
  color: var(--color-text-muted);
  font-size: 0.84em;
  min-height: 1.2em;
  text-align: center;
  max-width: 220px;
}

.error {
  color: var(--color-danger);
  font-size: 0.82em;
  text-align: center;
  max-width: 220px;
}
</style>
