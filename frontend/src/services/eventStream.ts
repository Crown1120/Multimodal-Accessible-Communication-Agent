// SSE 流式事件客户端（自动重连 + 指数退避 + Last-Event-ID 补齐 + 按 seq 幂等去重）
//
// 断线重连要点：
// 浏览器 EventSource 只在「同一个实例」自动重连时才会带 Last-Event-ID 请求头。
// 本项目在 onerror 里主动 close() 并新建实例（为了控制退避节奏），因此必须
// 自己把最后收到的 seq 作为查询参数带回，否则后端无法重放缺失事件。
// 后端同时支持 Last-Event-ID 头与 ?last_event_id= 查询参数。

import type { BridgeEvent } from '@/types'

const API_BASE = import.meta.env.VITE_API_BASE ?? '/api'

export type EventHandler = (event: BridgeEvent) => void

const TYPES: BridgeEvent['type'][] = [
  'transcript.partial',
  'transcript.final',
  'agent.started',
  'agent.thinking',
  'agent.completed',
  'tool.started',
  'tool.completed',
  'tool.failed',
  'message.delta',
  'message.completed',
  'digital_human.speak',
  'digital_human.audio_ready',
  'widget.show',
  'widget.update',
  'widget.close',
  'error',
]

/** 重连退避参数 */
const MAX_BACKOFF_MS = 30_000
const BASE_BACKOFF_MS = 1_000

/**
 * 订阅会话的流式事件（SSE），支持断线自动重连与事件补齐。
 * 返回取消订阅函数。
 */
export function subscribeEvents(sessionId: string, handler: EventHandler): () => void {
  const baseUrl = `${API_BASE}/sessions/${sessionId}/events`
  let es: EventSource | null = null
  let lastEventId = 0
  let reconnectAttempts = 0
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null
  let closed = false

  function connect() {
    if (closed) return
    // 带上 last_event_id，让后端重放断线期间缺失的事件
    const url = lastEventId > 0 ? `${baseUrl}?last_event_id=${lastEventId}` : baseUrl
    es = new EventSource(url)

    TYPES.forEach((type) => {
      es!.addEventListener(type, (raw) => {
        let payload: BridgeEvent
        try {
          payload = JSON.parse((raw as MessageEvent).data) as BridgeEvent
        } catch {
          return // 忽略解析失败
        }
        // 幂等：重放可能重复投递已处理过的事件，seq 不大于已处理的直接丢弃
        const seq = typeof payload.seq === 'number' ? payload.seq : 0
        if (seq > 0 && seq <= lastEventId) return
        if (seq > 0) lastEventId = seq
        handler(payload)
      })
    })

    es.onopen = () => {
      reconnectAttempts = 0
    }

    es.onerror = () => {
      if (closed) return
      es?.close()
      es = null
      const delay = Math.min(BASE_BACKOFF_MS * 2 ** reconnectAttempts, MAX_BACKOFF_MS)
      reconnectAttempts++
      console.warn(`[SSE] 连接断开，${delay}ms 后重连（第 ${reconnectAttempts} 次）`)
      reconnectTimer = setTimeout(connect, delay)
    }
  }

  connect()

  return () => {
    closed = true
    if (reconnectTimer) clearTimeout(reconnectTimer)
    es?.close()
    es = null
  }
}
