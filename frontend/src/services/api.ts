// API HTTP 客户端

import type { Message, Session, Mode, Scene } from '@/types'

const API_BASE = import.meta.env.VITE_API_BASE ?? '/api'

class ApiError extends Error {
  code: string
  details?: Record<string, unknown>
  constructor(code: string, message: string, details?: Record<string, unknown>) {
    super(message)
    this.code = code
    this.details = details
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const isForm = options.body instanceof FormData
  const headers: Record<string, string> = isForm ? {} : { 'Content-Type': 'application/json' }
  const resp = await fetch(`${API_BASE}${path}`, {
    headers: { ...headers, ...options.headers as Record<string, string> },
    ...options,
  })
  const data = await resp.json().catch(() => ({}))
  if (!resp.ok) {
    throw new ApiError(data.code ?? 'ERR_1000', data.message ?? `HTTP ${resp.status}`, data.details)
  }
  return data as T
}

export interface AudioTranscribeResult {
  session_id: string
  text: string
  message_id?: string
  ok: boolean
  asr_adapter?: string | null
}

export const api = {
  health: () => request<{ status: string; version: string; environment: string }>('/health'),

  createSession: async (payload: { scene?: Scene; mode?: Mode; user_id?: string | null }) => {
    const session = await request<Partial<Session>>('/sessions', {
      method: 'POST',
      body: JSON.stringify(payload),
    })
    if (!session.session_id) {
      throw new ApiError(
        'ERR_1000',
        '后端返回的不是 Bridge 会话，请确认后端地址和端口配置正确',
      )
    }
    return session as Session
  },

  getSession: (sessionId: string) => request<Session>(`/sessions/${sessionId}`),

  sendMessage: (sessionId: string, payload: { role: string; content: string; message_type?: string }) =>
    request<{ run_id: string }>(`/sessions/${sessionId}/messages`, {
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

  getMessages: (sessionId: string) =>
    request<Message[]>(`/sessions/${sessionId}/messages`),

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
