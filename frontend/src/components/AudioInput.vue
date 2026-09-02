<script setup lang="ts">
import { ref, onUnmounted } from 'vue'

import { useSessionStore } from '@/stores/session'

const store = useSessionStore()

const error = ref<string>('')
const interimText = ref<string>('')

// ---- 浏览器原生语音识别（Web Speech API）----
// 优先使用：无需 API Key，实时识别真实语音
// 注意：仅在安全源（localhost 或 HTTPS）下可用
const SpeechRecognitionCtor =
  (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition
const recognition = ref<any>(null)

function isSecureOrigin(): boolean {
  return (
    location.hostname === 'localhost' ||
    location.hostname === '127.0.0.1' ||
    location.protocol === 'https:'
  )
}

function isWebSpeechAvailable(): boolean {
  return !!SpeechRecognitionCtor && isSecureOrigin()
}

function startWebSpeech() {
  if (!store.sessionId || store.recording) return
  error.value = ''
  interimText.value = ''

  const rec = new SpeechRecognitionCtor()
  rec.lang = 'zh-CN'
  rec.continuous = false
  rec.interimResults = true

  rec.onresult = (event: any) => {
    let interim = ''
    let finalText = ''
    for (let i = event.resultIndex; i < event.results.length; i++) {
      const transcript = event.results[i][0].transcript
      if (event.results[i].isFinal) {
        finalText += transcript
      } else {
        interim += transcript
      }
    }
    // 实时增量字幕
    interimText.value = interim
    store.transcript = interim || finalText
    store.transcriptSpeaker = 'staff'

    if (finalText) {
      // 识别完成：推送为用户消息并触发 Agent
      store.transcript = ''
      store.transcriptSpeaker = ''
      interimText.value = ''
      store.sendMessage(finalText.trim())
    }
  }

  rec.onerror = (e: any) => {
    store.recording = false
    if (e.error === 'no-speech') {
      error.value = '未检测到语音，请重试'
    } else if (e.error === 'not-allowed') {
      error.value = '麦克风权限被拒绝，请在浏览器设置中允许'
    } else if (e.error === 'network' || e.error === 'service-not-allowed') {
      // Web Speech 不可用，回退到 MediaRecorder + 后端 ASR
      error.value = '浏览器语音识别不可用，正在切换到录音上传模式…'
      startRecording()
    } else {
      // 其他错误也回退
      error.value = `语音识别失败，正在切换到录音模式…`
      startRecording()
    }
  }

  rec.onend = () => {
    store.recording = false
    interimText.value = ''
    store.transcript = ''
    store.transcriptSpeaker = ''
  }

  rec.start()
  recognition.value = rec
  store.recording = true
}

function stopWebSpeech() {
  recognition.value?.stop()
  store.recording = false
}

// ---- 回退：MediaRecorder + 后端 ASR 上传 ----
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

onUnmounted(() => {
  recognition.value?.stop()
})
</script>

<template>
  <section class="audio-input" aria-label="语音输入">
    <button
      class="mic"
      :class="{ recording: store.recording }"
      :disabled="!store.sessionId"
      @click="store.recording ? stop() : start()"
      :aria-pressed="store.recording"
    >
      <span class="icon">{{ store.recording ? '⏹' : '🎤' }}</span>
      <span class="label">{{ store.recording ? '停止' : '说话' }}</span>
    </button>
    <div class="hint" v-if="store.recording && interimText">
      {{ interimText }}
    </div>
    <div class="hint" v-else-if="store.recording">正在聆听…</div>
    <div class="error" v-if="error" role="alert">{{ error }}</div>
  </section>
</template>

<style scoped>
.audio-input {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding: 8px;
}
.mic {
  display: flex;
  align-items: center;
  gap: 6px;
  border-radius: 999px;
  padding: 10px 18px;
  font-size: 1em;
}
.mic .icon {
  font-size: 1.2em;
}
.mic.recording {
  background: var(--color-danger);
  color: #fff;
  border-color: var(--color-danger);
  animation: recordPulse 1.2s ease-in-out infinite;
}
@keyframes recordPulse {
  0%,
  100% {
    box-shadow: 0 0 0 0 rgba(229, 72, 77, 0.4);
  }
  50% {
    box-shadow: 0 0 0 8px rgba(229, 72, 77, 0);
  }
}
.hint {
  color: var(--color-text-muted);
  font-size: 0.85em;
  min-height: 1.2em;
}
.error {
  color: var(--color-danger);
  font-size: 0.85em;
}
</style>
