// 会话 store 回归测试。
//
// 回归点：
// 1. speakingRunId 曾只在 setup 内部定义、未在 return 中导出，
//    DigitalHuman 运行时拿到 undefined，旧音频防串台守卫失效；
// 2. 轮椅开关状态曾不随消息上送，后端永远收不到 wheelchair。

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

import { useSessionStore } from '@/stores/session'

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('session store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('导出 speakingRunId（初始为 null）', () => {
    const store = useSessionStore()
    expect(store.speakingRunId).toBeNull()
  })

  it('setWheelchairMode 更新本地开关', () => {
    const store = useSessionStore()
    // 无会话时只更新本地状态，不发请求
    store.setWheelchairMode(true)
    expect(store.wheelchairMode).toBe(true)
  })

  it('sendMessage 把当前轮椅开关随消息上送', async () => {
    const fetchMock = vi.fn(async (_url: string, _init?: RequestInit) =>
      jsonResponse({ run_id: 'run_1', message_id: 'msg_1' }),
    )
    vi.stubGlobal('fetch', fetchMock)

    const store = useSessionStore()
    store.sessionId = 'sess_1'
    store.setWheelchairMode(true)
    await store.sendMessage('骨科怎么走')

    const call = fetchMock.mock.calls.find(([url]) => String(url).includes('/messages'))
    expect(call).toBeDefined()
    const body = JSON.parse(call![1]!.body as string)
    expect(body.wheelchair).toBe(true)
  })

  it('loadPreferences 回读 wheelchair_mode', async () => {
    const fetchMock = vi.fn(async (url: string) =>
      String(url).includes('/preferences')
        ? jsonResponse({
            font_size: 'large',
            speech_rate: 'slow',
            language: 'zh',
            high_contrast: false,
            wheelchair_mode: true,
            frequent_places: {},
          })
        : jsonResponse({}),
    )
    vi.stubGlobal('fetch', fetchMock)

    const store = useSessionStore()
    store.sessionId = 'sess_1'
    await store.loadPreferences()
    expect(store.wheelchairMode).toBe(true)
  })
})
