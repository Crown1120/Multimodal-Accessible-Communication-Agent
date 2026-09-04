// SSE 流式事件客户端（支持自动重连 + 指数退避 + Last-Event-ID 恢复）

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

/**
 * 订阅会话的流式事件（SSE），支持断线自动重连。
 * 返回取消订阅函数。
 */
export function subscribeEvents(sessionId: string, handler: EventHandler): () => void {
  const url = `${API_BASE}/sessions/${sessionId}/events`
  let es: EventSource | null = null
  let lastEventId = 0
  let reconnectAttempts = 0
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null
  let closed = false

  function connect() {
    if (closed) return
    es = new EventSource(url)

    TYPES.forEach((type) => {
      es!.addEventListener(type, (raw) => {
        try {
          const payload = JSON.parse((raw as MessageEvent).data) as BridgeEvent
          lastEventId = payload.seq || lastEventId
          handler(payload)
        } catch {
          // 忽略解析失败
        }
      })
    })

    es.onopen = () => {
      reconnectAttempts = 0
    }

    es.onerror = () => {
      if (closed) return
      es?.close()
      es = null
      // 指数退避：1s -> 2s -> 4s -> 8s -> 最大 30s
      const delay = Math.min(1000 * Math.pow(2, reconnectAttempts), 30000)
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
