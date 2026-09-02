// SSE 流式事件客户端

import type { BridgeEvent } from '@/types'

const API_BASE = import.meta.env.VITE_API_BASE ?? '/api'

export type EventHandler = (event: BridgeEvent) => void

/**
 * 订阅会话的流式事件（SSE）。
 * 返回取消订阅函数。
 */
export function subscribeEvents(sessionId: string, handler: EventHandler): () => void {
  const url = `${API_BASE}/sessions/${sessionId}/events`
  const es = new EventSource(url)

  const types: BridgeEvent['type'][] = [
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
    'widget.show',
    'widget.update',
    'widget.close',
    'error',
  ]

  types.forEach((type) => {
    es.addEventListener(type, (raw) => {
      try {
        const payload = JSON.parse((raw as MessageEvent).data) as BridgeEvent
        handler(payload)
      } catch {
        // 忽略解析失败
      }
    })
  })

  es.onerror = () => {
    // 前端可在 store 中展示连接断开并自动重连
  }

  return () => es.close()
}
