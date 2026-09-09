// 事件流客户端测试：断线重连必须携带 last_event_id，且重复事件按 seq 幂等丢弃。
//
// 这两个行为是 P1 修复的核心（此前 lastEventId 记录了但从不回传，
// 重连后事件会丢、消息会重复）。

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { subscribeEvents } from '@/services/eventStream'
import type { BridgeEvent } from '@/types'

type Listener = (ev: MessageEvent) => void

class FakeEventSource {
  static instances: FakeEventSource[] = []
  url: string
  onopen: (() => void) | null = null
  onerror: (() => void) | null = null
  closed = false
  private listeners = new Map<string, Listener[]>()

  constructor(url: string) {
    this.url = url
    FakeEventSource.instances.push(this)
  }

  addEventListener(type: string, cb: Listener) {
    const list = this.listeners.get(type) ?? []
    list.push(cb)
    this.listeners.set(type, list)
  }

  emit(event: BridgeEvent) {
    const payload = { data: JSON.stringify(event) } as MessageEvent
    ;(this.listeners.get(event.type) ?? []).forEach((cb) => cb(payload))
  }

  close() {
    this.closed = true
  }
}

function makeEvent(seq: number, type: BridgeEvent['type'] = 'message.delta'): BridgeEvent {
  return { type, session_id: 'sess_1', seq, data: { text: `t${seq}` } }
}

describe('subscribeEvents', () => {
  beforeEach(() => {
    FakeEventSource.instances = []
    vi.stubGlobal('EventSource', FakeEventSource)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('首次连接不带 last_event_id', () => {
    subscribeEvents('sess_1', vi.fn())
    expect(FakeEventSource.instances[0].url).toBe('/api/sessions/sess_1/events')
  })

  it('断线重连携带最后收到的 seq 作为 last_event_id', () => {
    vi.useFakeTimers()
    try {
      subscribeEvents('sess_1', vi.fn())
      const first = FakeEventSource.instances[0]
      first.emit(makeEvent(7))
      first.onerror?.()

      vi.runOnlyPendingTimers()

      const second = FakeEventSource.instances[1]
      expect(second.url).toBe('/api/sessions/sess_1/events?last_event_id=7')
    } finally {
      vi.useRealTimers()
    }
  })

  it('重放重复事件时按 seq 幂等去重', () => {
    const handler = vi.fn()
    subscribeEvents('sess_1', handler)
    const es = FakeEventSource.instances[0]

    es.emit(makeEvent(1))
    es.emit(makeEvent(2))
    es.emit(makeEvent(2)) // 重放
    es.emit(makeEvent(1)) // 重放

    expect(handler).toHaveBeenCalledTimes(2)
    expect(handler.mock.calls.map((c) => (c[0] as BridgeEvent).seq)).toEqual([1, 2])
  })

  it('取消订阅后关闭连接', () => {
    const unsubscribe = subscribeEvents('sess_1', vi.fn())
    const es = FakeEventSource.instances[0]
    unsubscribe()
    expect(es.closed).toBe(true)
  })

  it('忽略无法解析的事件数据', () => {
    const handler = vi.fn()
    subscribeEvents('sess_1', handler)
    const es = FakeEventSource.instances[0]
    const listeners = (
      es as unknown as { emit: (e: BridgeEvent) => void; listeners: Map<string, Listener[]> }
    ).listeners
    listeners.get('message.delta')?.forEach((cb) => cb({ data: 'not-json' } as MessageEvent))
    expect(handler).not.toHaveBeenCalled()
  })
})
