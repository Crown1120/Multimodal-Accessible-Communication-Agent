// API HTTP 客户端

import type { Message, Session, Mode, Scene } from '@/types'

const API_BASE = import.meta.env.VITE_API_BASE ?? '/api'

class ApiError extends Error {
  code: string
  details?: Record<string, unknown>
  status?: number
  constructor(code: string, message: string, details?: Record<string, unknown>, status?: number) {
    super(message)
    this.code = code
    this.details = details
    this.status = status
  }
}

async function request<T>(
  path: string,
  { timeout = 30000, headers: extraHeaders, ...options }: RequestInit & { timeout?: number } = {},
): Promise<T> {
  const isForm = options.body instanceof FormData
  const headers: Record<string, string> = isForm ? {} : { 'Content-Type': 'application/json' }
  const controller = new AbortController()
  const timeoutId = setTimeout(() => controller.abort(), timeout)
  try {
    // 注意：options 已被解构（headers/timeout 已剔除），这里再展开不会覆盖上面的 headers
    const resp = await fetch(`${API_BASE}${path}`, {
      ...options,
      headers: { ...headers, ...(extraHeaders as Record<string, string> | undefined) },
      signal: controller.signal,
    })
    const data = await resp.json().catch(() => ({}))
    if (!resp.ok) {
      throw new ApiError(
        data.code ?? 'ERR_1000',
        data.message ?? `HTTP ${resp.status}`,
        data.details,
        resp.status,
      )
    }
    return data as T
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw new ApiError('ERR_TIMEOUT', '请求超时，请检查网络连接或稍后重试')
    }
    throw error
  } finally {
    clearTimeout(timeoutId)
  }
}


export interface AudioTranscribeResult {
  session_id: string
  text: string
  message_id?: string
  run_id?: string | null
  ok: boolean
  asr_adapter?: string | null
}

export interface SendMessageResult {
  run_id: string
  message_id: string
}

export interface PublicConfig {
  xingyun_app_id: string
  xingyun_app_secret: string
  xingyun_gateway: string
  max_message_length: number
  max_upload_mb: number
}

export const api = {
  health: () => request<{ status: string; version: string; environment: string }>('/health'),

  /** 运行时公开配置（数字人凭据等），避免把凭据内联进静态产物 */
  getPublicConfig: () => request<PublicConfig>('/config/public'),

  createSession: async (payload: { scene?: Scene; mode?: Mode; user_id?: string | null }) => {
    const session = await request<Partial<Session>>('/sessions', {
      method: 'POST',
      body: JSON.stringify(payload),
    })
    if (!session.session_id) {
      throw new ApiError('ERR_1000', '后端返回的不是 Bridge 会话，请确认后端地址和端口配置正确')
    }
    return session as Session
  },

  getSession: (sessionId: string) => request<Session>(`/sessions/${sessionId}`),

  sendMessage: (
    sessionId: string,
    payload: { role: string; content: string; message_type?: string; wheelchair?: boolean },
  ) =>
    request<SendMessageResult>(`/sessions/${sessionId}/messages`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  uploadAudio: (
    sessionId: string,
    audio: Blob,
    opts: { speaker?: string; language?: string } = {},
  ) => {
    const form = new FormData()
    form.append('audio', audio, 'audio.webm')
    if (opts.speaker) form.append('speaker', opts.speaker)
    if (opts.language) form.append('language', opts.language)
    return request<AudioTranscribeResult>(`/sessions/${sessionId}/audio`, {
      method: 'POST',
      body: form,
    })
  },

  analyzeImage: (sessionId: string, imageFile: File) => {
    const form = new FormData()
    form.append('image', imageFile, 'report.jpg')
    return request<{ analysis: string; summary: string }>(`/sessions/${sessionId}/analyze-image`, {
      method: 'POST',
      body: form,
    })
  },

  getMessages: (sessionId: string) => request<Message[]>(`/sessions/${sessionId}/messages`),

  getPreferences: (sessionId: string) =>
    request<Record<string, unknown> | null>(`/sessions/${sessionId}/preferences`),

  savePreferences: (
    sessionId: string,
    payload: {
      mode?: string
      font_size?: string
      speech_rate?: string
      language?: string
      high_contrast?: boolean
      frequent_places?: Record<string, unknown>
    },
  ) =>
    request<Record<string, unknown>>(`/sessions/${sessionId}/preferences`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    }),

  clearPreferences: (sessionId: string) =>
    request<{ cleared: boolean }>(`/sessions/${sessionId}/preferences`, {
      method: 'DELETE',
    }),

  getWidget: (widgetId: string) =>
    request<{ widget_id: string; widget_type: string; payload: Record<string, unknown> }>(
      `/widgets/${widgetId}`,
    ),
}

export { ApiError }
