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
export function subscribeEvents(
  sessionId: string,
  handler: EventHandler,
  initialLastEventId = 0,
): () => void {
  const baseUrl = `${API_BASE}/sessions/${sessionId}/events`
  let es: EventSource | null = null
  // initialLastEventId：首次连接时告诉后端从哪个 seq 之后开始推送。
  // 恢复会话时传入极大值（Number.MAX_SAFE_INTEGER），让后端不重放历史事件；
  // 新建会话时默认 0，不重放（新会话本无历史）。
  // 注意：它只用于首次连接的请求参数，绝不能用它做幂等去重，
  // 否则所有新事件的 seq 都会被误判为「已处理」而丢弃。
  let firstConnect = true
  let processedSeq = 0
  let reconnectAttempts = 0
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null
  let closed = false

  function connect() {
    if (closed) return
    // 首次连接按 initialLastEventId 控制重放；
    // 断线重连按 processedSeq 让后端补齐缺失事件
    const replayFrom = firstConnect ? initialLastEventId : processedSeq
    firstConnect = false
    const url = replayFrom > 0 ? `${baseUrl}?last_event_id=${replayFrom}` : baseUrl
    es = new EventSource(url)

    TYPES.forEach((type) => {
      es!.addEventListener(type, (raw) => {
        let payload: BridgeEvent
        try {
          payload = JSON.parse((raw as MessageEvent).data) as BridgeEvent
        } catch {
          return // 忽略解析失败
        }
        // 幂等去重基于 processedSeq（已处理的最大 seq），
        // 与 initialLastEventId 无关，避免恢复会话时丢弃所有新事件
        const seq = typeof payload.seq === 'number' ? payload.seq : 0
        if (seq > 0 && seq <= processedSeq) return
        if (seq > 0) processedSeq = seq
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
