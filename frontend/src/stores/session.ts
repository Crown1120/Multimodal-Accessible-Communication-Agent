// 会话与沟通状态 Store

import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { api } from '@/services/api'
import { subscribeEvents, type EventHandler } from '@/services/eventStream'
import type { AgentStatus, BridgeEvent, Message, Mode, Scene, WidgetData } from '@/types'

export const useSessionStore = defineStore('session', () => {
  // 状态
  const sessionId = ref<string | null>(null)
  const scene = ref<Scene>('hospital')
  const mode = ref<Mode>('standard')
  const status = ref<'disconnected' | 'connecting' | 'connected' | 'error'>('disconnected')
  const messages = ref<Message[]>([])
  const transcript = ref<string>('') // 实时增量字幕（含 ASR 与数字人播报）
  const transcriptSpeaker = ref<string>('') // 当前字幕说话人
  const agentStatus = ref<AgentStatus>('idle')
  const agentDetail = ref<string>('')
  const speaking = ref<boolean>(false) // 数字人是否正在播报
  const speakingText = ref<string>('')
  const speakingAudioUrl = ref<string | null>(null) // 数字人语音 URL
  const speakingSpeed = ref<number>(1.0) // 播报语速
  const needRepeat = ref<boolean>(false) // 重要信息需重复确认
  const speakingGesture = ref<string>('idle') // 数字人手势动作
  const speakingExpression = ref<string>('neutral') // 数字人表情
  const widgets = ref<WidgetData[]>([])
  const recording = ref<boolean>(false) // 是否正在录音
  const lastError = ref<string>('') // 最近错误提示

  // 独立无障碍偏好（可手动调整，随模式联动但有独立覆盖）
  const fontSize = ref<'small' | 'medium' | 'large'>('medium')
  const speechRate = ref<'normal' | 'slow'>('normal')
  const highContrast = ref<boolean>(false)

  let unsubscribe: (() => void) | null = null

  const isConnected = computed(() => status.value === 'connected')

  // 无障碍偏好：模式联动 + 独立覆盖
  const isHighContrast = computed(
    () => highContrast.value || mode.value === 'hearing',
  )
  const isLargeFont = computed(
    () => fontSize.value === 'large' || mode.value !== 'standard',
  )
  const isSlowSpeech = computed(
    () => speechRate.value === 'slow' || mode.value !== 'standard',
  )

  // 创建会话
  async function createSession() {
    status.value = 'connecting'
    try {
      // 清空上一轮会话的状态
      unsubscribe?.()
      unsubscribe = null
      messages.value = []
      widgets.value = []
      transcript.value = ''
      transcriptSpeaker.value = ''
      agentStatus.value = 'idle'
      agentDetail.value = ''
      speaking.value = false
      speakingText.value = ''
      lastError.value = ''

      const res = await api.createSession({ scene: scene.value, mode: mode.value })
      sessionId.value = res.session_id
      mode.value = res.mode
      scene.value = res.scene
      status.value = 'connected'
      subscribe()
      // 加载已保存的用户偏好
      await loadPreferences()
    } catch (e) {
      status.value = 'error'
      throw e
    }
  }

  // 订阅流式事件
  function subscribe() {
    if (!sessionId.value) return
    unsubscribe?.()
    const handler: EventHandler = (event: BridgeEvent) => handleEvent(event)
    unsubscribe = subscribeEvents(sessionId.value, handler)
  }

  function handleEvent(event: BridgeEvent) {
    const d = event.data
    switch (event.type) {
      case 'transcript.partial':
        transcript.value = (d.text as string) ?? ''
        transcriptSpeaker.value = (d.speaker as string) ?? ''
        break
      case 'transcript.final':
        transcript.value = ''
        transcriptSpeaker.value = ''
        messages.value.push({
          id: crypto.randomUUID(),
          session_id: event.session_id,
          // 语音转写的用户消息显示在右侧（与文字输入一致）
          role: d.speaker === 'assistant' ? 'assistant' : 'user',
          content: (d.text as string) ?? '',
          speaker: d.speaker as string,
          message_type: 'transcript',
        })
        break
      case 'agent.started':
        agentStatus.value = 'running'
        agentDetail.value = d.intent ? `识别意图：${d.intent}` : ''
        break
      case 'agent.thinking':
        agentStatus.value = 'thinking'
        agentDetail.value = (d.detail as string) ?? (d.step as string) ?? ''
        break
      case 'agent.completed':
        agentStatus.value = 'completed'
        agentDetail.value = (d.summary as string) ?? ''
        setTimeout(() => (agentStatus.value = 'idle'), 1500)
        break
      case 'message.delta':
        // 增量合并到最后一条 assistant 消息
        if (messages.value.at(-1)?.role !== 'assistant') {
          messages.value.push({
            id: crypto.randomUUID(),
            session_id: event.session_id,
            role: 'assistant',
            content: '',
          })
        }
        {
          const last = messages.value.at(-1)!
          last.content += (d.text as string) ?? ''
          // 数字人正在播报，同步驱动字幕
          speaking.value = true
          speakingText.value = last.content
          transcript.value = last.content
          transcriptSpeaker.value = 'assistant'
        }
        break
      case 'message.completed': {
        // 优先按 message_id 匹配；找不到则更新最后一条 assistant 消息（避免重复）
        const content = (d.content as string) ?? ''
        let idx = d.message_id ? messages.value.findIndex((m) => m.id === d.message_id) : -1
        if (idx < 0) {
          // delta 阶段用随机 UUID 创建的消息，用最后一条 assistant 消息替换
          idx = messages.value.findIndex((m, i) => m.role === 'assistant' && i === messages.value.length - 1)
        }
        if (idx >= 0) {
          messages.value[idx].id = (d.message_id as string) ?? messages.value[idx].id
          messages.value[idx].content = content
        } else {
          messages.value.push({
            id: (d.message_id as string) ?? crypto.randomUUID(),
            session_id: event.session_id,
            role: d.role as Message['role'],
            content,
          })
        }
        // 播报完成，清空实时字幕
        speaking.value = false
        speakingText.value = ''
        speakingAudioUrl.value = null
        needRepeat.value = false
        transcript.value = ''
        transcriptSpeaker.value = ''
        break
      }
      case 'digital_human.speak':
        speaking.value = true
        speakingText.value = (d.text as string) ?? ''
        transcript.value = (d.text as string) ?? ''
        transcriptSpeaker.value = 'assistant'
        speakingAudioUrl.value = (d.audio_url as string) ?? null
        speakingSpeed.value = (d.speed as number) ?? 1.0
        needRepeat.value = (d.repeat as boolean) ?? false
        speakingGesture.value = (d.gesture as string) ?? 'idle'
        speakingExpression.value = (d.expression as string) ?? 'neutral'
        break
      case 'widget.show': {
        // 按 widget_id 去重：同 ID 的 widget 替换而非追加，避免重复展示
        const wId = d.widget_id as string
        const existing = widgets.value.find((x) => x.widget_id === wId)
        if (existing) {
          existing.widget_type = (d.widget_type as WidgetData['widget_type']) ?? existing.widget_type
          existing.payload = (d.payload as Record<string, unknown>) ?? existing.payload
        } else {
          widgets.value.push({
            widget_id: wId,
            widget_type: d.widget_type as WidgetData['widget_type'],
            payload: (d.payload as Record<string, unknown>) ?? {},
          })
        }
        break
      }
      case 'widget.update': {
        const w = widgets.value.find((x) => x.widget_id === d.widget_id)
        if (w) Object.assign(w.payload, d.payload)
        break
      }
      case 'widget.close':
        widgets.value = widgets.value.filter((x) => x.widget_id !== d.widget_id)
        break
      case 'error':
        lastError.value = (d.message as string) ?? '发生未知错误'
        setTimeout(() => (lastError.value = ''), 5000)
        break
    }
  }

  // 发送消息
  async function sendMessage(content: string) {
    if (!sessionId.value) return
    messages.value.push({
      id: crypto.randomUUID(),
      session_id: sessionId.value,
      role: 'user',
      content,
    })
    await api.sendMessage(sessionId.value, { role: 'user', content })
  }

  // 上传音频（ASR 转字幕 + 触发 Agent）
  async function uploadAudio(audio: Blob, speaker = 'staff') {
    if (!sessionId.value) return
    recording.value = false
    try {
      const res = await api.uploadAudio(sessionId.value, audio, { speaker })
      if (!res.ok) {
        lastError.value = '语音识别失败，请重试或使用文字输入'
      }
    } catch {
      lastError.value = '音频上传失败，请检查网络后重试'
    }
  }

  // 切换模式（同步保存偏好到后端）
  function setMode(m: Mode) {
    mode.value = m
    document.documentElement.setAttribute('data-mode', m)
    // 模式联动默认值
    if (m === 'hearing') {
      fontSize.value = 'large'
      speechRate.value = 'slow'
      highContrast.value = true
    } else if (m === 'elderly') {
      fontSize.value = 'large'
      speechRate.value = 'slow'
      highContrast.value = false
    } else {
      fontSize.value = 'medium'
      speechRate.value = 'normal'
      highContrast.value = false
    }
    applyAccessibilityAttrs()
    // 模式切换时持久化偏好
    if (sessionId.value) {
      api
        .savePreferences(sessionId.value, {
          mode: m,
          font_size: fontSize.value,
          speech_rate: speechRate.value,
          high_contrast: highContrast.value,
        })
        .catch(() => {})
    }
  }

  // 应用无障碍属性到 <html>，供 CSS 联动
  function applyAccessibilityAttrs() {
    const el = document.documentElement
    el.setAttribute('data-font-size', fontSize.value)
    el.setAttribute('data-contrast', highContrast.value ? 'on' : 'off')
    el.setAttribute('data-speech', speechRate.value)
  }

  // 手动设置独立偏好（不切换模式）
  function setFontSize(size: 'small' | 'medium' | 'large') {
    fontSize.value = size
    applyAccessibilityAttrs()
    if (sessionId.value) {
      api
        .savePreferences(sessionId.value, { font_size: size })
        .catch(() => {})
    }
  }

  function setSpeechRate(rate: 'normal' | 'slow') {
    speechRate.value = rate
    applyAccessibilityAttrs()
    if (sessionId.value) {
      api
        .savePreferences(sessionId.value, { speech_rate: rate })
        .catch(() => {})
    }
  }

  function setHighContrast(on: boolean) {
    highContrast.value = on
    applyAccessibilityAttrs()
    if (sessionId.value) {
      api
        .savePreferences(sessionId.value, { high_contrast: on })
        .catch(() => {})
    }
  }

  // 加载用户偏好
  async function loadPreferences() {
    if (!sessionId.value) return
    try {
      const pref = await api.getPreferences(sessionId.value)
      if (pref) {
        const savedMode = pref.mode as Mode | undefined
        if (savedMode) {
          mode.value = savedMode
          document.documentElement.setAttribute('data-mode', savedMode)
        }
        if (pref.font_size) fontSize.value = pref.font_size as 'small' | 'medium' | 'large'
        if (pref.speech_rate) speechRate.value = pref.speech_rate as 'normal' | 'slow'
        if (pref.high_contrast !== undefined) highContrast.value = pref.high_contrast as boolean
        applyAccessibilityAttrs()
      }
    } catch {
      // 偏好加载失败不阻断流程
    }
  }

  // 清除用户偏好
  async function clearPreferences() {
    if (!sessionId.value) return
    try {
      await api.clearPreferences(sessionId.value)
      // 重置为默认
      fontSize.value = 'medium'
      speechRate.value = 'normal'
      highContrast.value = false
      applyAccessibilityAttrs()
    } catch {
      lastError.value = '清除偏好失败'
    }
  }

  function $reset() {
    unsubscribe?.()
    unsubscribe = null
    sessionId.value = null
    status.value = 'disconnected'
    messages.value = []
    transcript.value = ''
    transcriptSpeaker.value = ''
    agentStatus.value = 'idle'
    agentDetail.value = ''
    speaking.value = false
    speakingText.value = ''
    speakingAudioUrl.value = null
    needRepeat.value = false
    speakingGesture.value = 'idle'
    speakingExpression.value = 'neutral'
    recording.value = false
    lastError.value = ''
    widgets.value = []
    fontSize.value = 'medium'
    speechRate.value = 'normal'
    highContrast.value = false
    document.documentElement.removeAttribute('data-font-size')
    document.documentElement.removeAttribute('data-contrast')
    document.documentElement.removeAttribute('data-speech')
  }

  return {
    sessionId,
    scene,
    mode,
    status,
    messages,
    transcript,
    transcriptSpeaker,
    agentStatus,
    agentDetail,
    speaking,
    speakingText,
    speakingAudioUrl,
    speakingSpeed,
    needRepeat,
    speakingGesture,
    speakingExpression,
    widgets,
    recording,
    lastError,
    fontSize,
    speechRate,
    highContrast,
    isConnected,
    isHighContrast,
    isLargeFont,
    isSlowSpeech,
    createSession,
    sendMessage,
    uploadAudio,
    setMode,
    setFontSize,
    setSpeechRate,
    setHighContrast,
    loadPreferences,
    clearPreferences,
    $reset,
  }
})
