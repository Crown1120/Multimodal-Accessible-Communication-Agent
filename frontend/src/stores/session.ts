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
  const speakingRunId = ref<string | null>(null) // 当前播报所属 run_id（防异步音频串消息）
  const speakingGesture = ref<string>('idle') // 数字人手势动作
  const speakingExpression = ref<string>('neutral') // 数字人表情
  // 本地播报请求计数：由 speak() 递增，驱动 DigitalHuman 立即播报
  // （区别于 SSE 的 digital_human.speak，后者要等 TTS 音频就绪）
  const speakTick = ref<number>(0)
  const widgets = ref<WidgetData[]>([])
  const recording = ref<boolean>(false) // 是否正在录音
  const sending = ref<boolean>(false) // 是否正在发送消息
  const flash = ref<boolean>(false) // 听障模式闪光通知
const wheelchairMode = ref<boolean>(false) // 轮椅模式（无障碍路线）
const emotion = ref<string>('neutral') // 当前对话情绪（neutral/anxious/painful/calm/happy）
const emotionConfidence = ref<number>(0) // 情绪识别置信度
  const lastError = ref<string>('') // 最近错误提示
  const asrAdapter = ref<string>('') // 当前实际使用的ASR适配器（豆包大模型/Whisper离线/Vosk离线/演示模式）
  // 后端公开配置（输入长度上限等），由 loadPublicConfig 拉取
  const maxMessageLength = ref<number>(2000)
  const maxUploadMb = ref<number>(10)

  // 独立无障碍偏好（可手动调整，随模式联动但有独立覆盖）
  const fontSize = ref<'small' | 'medium' | 'large'>('medium')
  const speechRate = ref<'normal' | 'slow'>('normal')
  const highContrast = ref<boolean>(false)

  let unsubscribe: (() => void) | null = null
  // 待清理的定时器句柄（切换会话 / 卸载时统一清除，避免旧定时器污染新会话状态）
  let flashTimer: ReturnType<typeof setTimeout> | null = null
  let agentIdleTimer: ReturnType<typeof setTimeout> | null = null
  let errorTimer: ReturnType<typeof setTimeout> | null = null

  function clearTimers() {
    if (flashTimer !== null) {
      clearTimeout(flashTimer)
      flashTimer = null
    }
    if (agentIdleTimer !== null) {
      clearTimeout(agentIdleTimer)
      agentIdleTimer = null
    }
    if (errorTimer !== null) {
      clearTimeout(errorTimer)
      errorTimer = null
    }
  }

  const isConnected = computed(() => status.value === 'connected')

  // 无障碍偏好：模式联动 + 独立覆盖
  const isHighContrast = computed(() => highContrast.value || mode.value === 'hearing')
  const isLargeFont = computed(() => fontSize.value === 'large' || mode.value !== 'standard')
  const isSlowSpeech = computed(() => speechRate.value === 'slow' || mode.value !== 'standard')

  // 创建会话
  async function createSession() {
    status.value = 'connecting'
    try {
      // 清空上一轮会话的状态
      unsubscribe?.()
      unsubscribe = null
      clearTimers()
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
      // 持久化 sessionId，刷新页面后可恢复
      try {
        localStorage.setItem('bridge_session_id', res.session_id)
      } catch {
        /* ignore */
      }
      subscribe()
      // 加载已保存的用户偏好
      await loadPreferences()
      await loadPublicConfig()
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
      case 'transcript.final': {
        transcript.value = ''
        transcriptSpeaker.value = ''
        // 优先使用服务端持久化消息的 ID，保证与历史记录一致（避免刷新后出现重复消息）
        const serverId = (d.message_id as string) || crypto.randomUUID()
        if (messages.value.some((m) => m.id === serverId)) break
        messages.value.push({
          id: serverId,
          session_id: event.session_id,
          // 语音转写的用户消息显示在右侧（与文字输入一致）
          role: d.speaker === 'assistant' ? 'assistant' : 'user',
          content: (d.text as string) ?? '',
          speaker: d.speaker as string,
          message_type: 'transcript',
          send_status: 'sent',
        })
        break
      }
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
        if (agentIdleTimer !== null) clearTimeout(agentIdleTimer)
        agentIdleTimer = setTimeout(() => {
          agentStatus.value = 'idle'
          agentIdleTimer = null
        }, 1500)
        break
      case 'message.delta': {
        // Use the run ID so interleaved or replayed events cannot update another reply.
        const deltaRunId = d.run_id as string | undefined
        let deltaMessage = deltaRunId
          ? messages.value.find((m) => m.run_id === deltaRunId)
          : undefined
        if (!deltaMessage) {
          messages.value.push({
            id: crypto.randomUUID(),
            session_id: event.session_id,
            role: 'assistant',
            content: '',
            run_id: deltaRunId,
          })
          deltaMessage = messages.value.at(-1)
        }
        {
          deltaMessage!.content += (d.text as string) ?? ''
          // 流式文本仅用于消息列表与实时字幕展示；
          // 数字人播报统一由 digital_human.speak 触发，
          // 避免流式期间提前驱动字幕/嘴型导致与 TTS 音频不同步
          transcript.value = deltaMessage!.content
          transcriptSpeaker.value = 'assistant'
        }
        break
      }
      case 'message.completed': {
        // 优先按 message_id 匹配；找不到则更新最后一条 assistant 消息（避免重复）
        const content = (d.content as string) ?? ''
        let idx = d.message_id ? messages.value.findIndex((m) => m.id === d.message_id) : -1
        if (idx < 0 && d.run_id) idx = messages.value.findIndex((m) => m.run_id === d.run_id)
        if (idx >= 0) {
          const serverId = d.message_id as string | undefined
          // 仅在没有其他消息占用该 ID 时回写，避免列表出现重复 key
          if (serverId && !messages.value.some((m, i) => i !== idx && m.id === serverId)) {
            messages.value[idx].id = serverId
          }
          messages.value[idx].content = content
          messages.value[idx].send_status = 'sent'
        } else {
          messages.value.push({
            id: (d.message_id as string) ?? crypto.randomUUID(),
            session_id: event.session_id,
            role: d.role as Message['role'],
            content,
            run_id: d.run_id as string | undefined,
          })
        }
        // 播报完成，清空实时字幕
        speaking.value = false
        stopFlash()
        speakingText.value = ''
        speakingAudioUrl.value = null
        speakingRunId.value = null
        needRepeat.value = false
        transcript.value = ''
        transcriptSpeaker.value = ''
        break
      }
      case 'digital_human.speak':
        speaking.value = true
        flashNotification()
        speakingText.value = (d.text as string) ?? ''
        transcript.value = (d.text as string) ?? ''
        transcriptSpeaker.value = 'assistant'
        // TTS 异步化：speak 事件可能不含音频（audio_url 为 null），
        // 音频稍后通过 digital_human.audio_ready 事件推送
        speakingAudioUrl.value = (d.audio_url as string) ?? null
        speakingSpeed.value = (d.speed as number) ?? 1.0
        speakingRunId.value = (d.run_id as string) ?? null
        needRepeat.value = (d.repeat as boolean) ?? false
        speakingGesture.value = (d.gesture as string) ?? 'idle'
        speakingExpression.value = (d.expression as string) ?? 'neutral'
        break
      case 'digital_human.audio_ready':
        // 异步 TTS 音频就绪：仅接受当前播报 run_id 的音频，
        // 防止上一条消息的慢音频覆盖新播报
        if (speaking.value && (!speakingRunId.value || d.run_id === speakingRunId.value)) {
          speakingAudioUrl.value = (d.audio_url as string) ?? null
        }
        break
      case 'widget.show': {
        // 按 widget_id 去重：同 ID 的 widget 替换而非追加，避免重复展示
        const wId = d.widget_id as string
        const existing = widgets.value.find((x) => x.widget_id === wId)
        if (existing) {
          existing.widget_type =
            (d.widget_type as WidgetData['widget_type']) ?? existing.widget_type
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
        if (errorTimer !== null) clearTimeout(errorTimer)
        errorTimer = setTimeout(() => {
          lastError.value = ''
          errorTimer = null
        }, 5000)
        break
    }
  }

  // 发送消息
  async function sendMessage(content: string) {
    if (!sessionId.value || sending.value) return
    sending.value = true
    const localId = crypto.randomUUID()
    messages.value.push({
      id: localId,
      session_id: sessionId.value,
      role: 'user',
      content,
      send_status: 'pending',
    })
    try {
      const res = await api.sendMessage(sessionId.value, { role: 'user', content })
      const localMessage = messages.value.find((m) => m.id === localId)
      if (localMessage) {
        // 回写服务端 message_id，使后续事件/历史记录按同一 ID 关联；
        // 保留 localId 到服务端 ID 的映射前，先确认没有同 ID 的消息（避免 key 冲突）
        if (res.message_id && !messages.value.some((m) => m.id === res.message_id)) {
          localMessage.id = res.message_id
        }
        localMessage.send_status = 'sent'
      }
    } catch (error) {
      const localMessage = messages.value.find((m) => m.id === localId)
      if (localMessage) localMessage.send_status = 'failed'
      throw error
    } finally {
      sending.value = false
    }
  }

  // 听障模式闪光通知：播报期间持续闪烁页面边框
  function flashNotification() {
    if (mode.value !== 'hearing') return
    flash.value = true
    // 兜底：若 message.completed / 播报结束事件丢失，30s 后自动停止闪烁，
    // 避免边框无限闪烁（对光敏用户有害）
    if (flashTimer !== null) clearTimeout(flashTimer)
    flashTimer = setTimeout(() => {
      flash.value = false
  wheelchairMode.value = false
  emotion.value = 'neutral'
  emotionConfidence.value = 0
      flashTimer = null
    }, 30000)
  }
  // 停止闪光通知
  function stopFlash() {
    if (flashTimer !== null) {
      clearTimeout(flashTimer)
      flashTimer = null
    }
    flash.value = false
  wheelchairMode.value = false
  emotion.value = 'neutral'
  emotionConfidence.value = 0
  }

  /**
   * 本地播报一段文本（「重复一遍」按钮、路线语音导航）。
   *
   * 与 SSE 的 digital_human.speak 不同：这里没有后端 TTS 音频，
   * 通过递增 speakTick 让 DigitalHuman 立即用 SDK / 浏览器 TTS 播报，
   * 不必等 4 秒的音频兜底定时器。
   */
  function speak(
    text: string,
    opts: { speed?: number; gesture?: string; expression?: string } = {},
  ) {
    const content = (text || '').trim()
    if (!content) return
    speaking.value = true
    speakingText.value = content
    speakingAudioUrl.value = null
    speakingRunId.value = null
    speakingSpeed.value = opts.speed ?? 1.0
    speakingGesture.value = opts.gesture ?? 'idle'
    speakingExpression.value = opts.expression ?? 'neutral'
    needRepeat.value = false
    transcript.value = content
    transcriptSpeaker.value = 'assistant'
    flashNotification()
    speakTick.value += 1
  }

  // 上传音频（ASR 转字幕 + 触发 Agent）
  async function uploadAudio(audio: Blob, speaker = 'staff') {
    if (!sessionId.value) return
    recording.value = false
    // 上传前先按后端上限做本地校验，避免白传一个大文件再被 413 拒绝
    const limitBytes = maxUploadMb.value * 1024 * 1024
    if (limitBytes > 0 && audio.size > limitBytes) {
      lastError.value = `录音过长（超过 ${maxUploadMb.value} MB），请缩短后再试`
      return
    }
    try {
      const res = await api.uploadAudio(sessionId.value, audio, { speaker })
      if (!res.ok) {
        lastError.value = '语音识别失败，请重试或使用文字输入'
      } else if (res.asr_adapter) {
        asrAdapter.value = res.asr_adapter
      }
    } catch {
      lastError.value = '音频上传失败，请检查网络后重试'
    }
  }

  // 切换模式（同步保存偏好到后端）
  function setMode(m: Mode) {
    mode.value = m
    document.documentElement.setAttribute('data-mode', m)
    // 强制重排：解决 CSS 变量变化时已存在元素样式不重新计算的浏览器优化问题
    // 需等待 CSS 变量更新后（约 50ms）再触发重排
    setTimeout(() => {
      document.body.style.display = 'none'
      void document.body.offsetHeight
      document.body.style.display = ''
    }, 50)
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
      api.savePreferences(sessionId.value, { font_size: size }).catch(() => {})
    }
  }

  function setSpeechRate(rate: 'normal' | 'slow') {
    speechRate.value = rate
    applyAccessibilityAttrs()
    if (sessionId.value) {
      api.savePreferences(sessionId.value, { speech_rate: rate }).catch(() => {})
    }
  }

  function setHighContrast(on: boolean) {
    highContrast.value = on
    applyAccessibilityAttrs()
    if (sessionId.value) {
      api.savePreferences(sessionId.value, { high_contrast: on }).catch(() => {})
    }
  }

  // 加载后端公开配置（输入长度上限等），失败时保留默认值
  async function loadPublicConfig() {
    try {
      const cfg = await api.getPublicConfig()
      if (cfg.max_message_length > 0) maxMessageLength.value = cfg.max_message_length
      if (cfg.max_upload_mb > 0) maxUploadMb.value = cfg.max_upload_mb
    } catch {
      // 后端不可用时保持默认值
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

  // 恢复已有会话（刷新页面后自动恢复，无需重新创建）
  async function restoreSession(): Promise<boolean> {
    let savedId: string | null = null
    try {
      savedId = localStorage.getItem('bridge_session_id')
    } catch {
      /* ignore */
    }
    if (!savedId) return false
    try {
      // 验证会话是否有效
      const session = await api.getSession(savedId)
      if (!session || session.status === 'closed') {
        try {
          localStorage.removeItem('bridge_session_id')
        } catch {
          /* ignore */
        }
        return false
      }
      // 恢复状态
      sessionId.value = savedId
      mode.value = (session.mode as Mode) || mode.value
      scene.value = (session.scene as Scene) || scene.value
      status.value = 'connected'
      // 同步无障碍属性，保证恢复后样式与模式一致
      document.documentElement.setAttribute('data-mode', mode.value)
      applyAccessibilityAttrs()
      // 加载消息历史
      try {
        const history = await api.getMessages(savedId)
        messages.value = history.map((m) => ({
          id: m.id,
          session_id: m.session_id,
          role: m.role as Message['role'],
          content: m.content,
          speaker: m.speaker,
          language: m.language,
          message_type: m.message_type as Message['message_type'],
          send_status: 'sent',
        }))
      } catch {
        /* 历史加载失败不阻断 */
      }
      subscribe()
      await loadPreferences()
      await loadPublicConfig()
      return true
    } catch {
      // 会话不存在或已失效，清除并返回 false
      try {
        localStorage.removeItem('bridge_session_id')
      } catch {
        /* ignore */
      }
      return false
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
    clearTimers()
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
    speakingRunId.value = null
    needRepeat.value = false
    speakingGesture.value = 'idle'
    speakingExpression.value = 'neutral'
    recording.value = false
    lastError.value = ''
    asrAdapter.value = ''
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
    speakTick,
    widgets,
    recording,
    lastError,
    asrAdapter,
    maxMessageLength,
    maxUploadMb,
    fontSize,
    speechRate,
    highContrast,
    isConnected,
    sending,
    flash,
    flashNotification,
    stopFlash,
    wheelchairMode,
    setWheelchairMode,
    emotion,
    emotionConfidence,
    setEmotion,
    speak,
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
    restoreSession,
    clearPreferences,
    $reset,
  }
})
