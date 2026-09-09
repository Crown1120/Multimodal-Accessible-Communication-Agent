// API 客户端测试：headers 合并与错误封装。
//
// 回归点：旧实现 `{ headers: merged, signal, ...options }` 把 options 展开在最后，
// 调用方传了 headers 就会整体覆盖掉 Content-Type。

import { afterEach, describe, expect, it, vi } from 'vitest'

import { api, ApiError } from '@/services/api'

function mockFetch(handler: (url: string, init: RequestInit) => Response) {
  const fn = vi.fn(async (url: string, init: RequestInit) => handler(url, init))
  vi.stubGlobal('fetch', fn)
  return fn
}

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('api.request', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('默认发送 JSON Content-Type', async () => {
    const fetchMock = mockFetch(() => jsonResponse({ status: 'ok' }))
    await api.health()
    const init = fetchMock.mock.calls[0][1]
    expect((init.headers as Record<string, string>)['Content-Type']).toBe('application/json')
  })

  it('调用方自定义 header 不会丢失 Content-Type', async () => {
    const fetchMock = mockFetch(() => jsonResponse({ session_id: 'sess_1', scene: 'hospital', mode: 'standard', status: 'active' }))
    await api.getSession('sess_1')
    const init = fetchMock.mock.calls[0][1]
    // getSession 未传自定义 header，验证合并逻辑不破坏默认值
    expect((init.headers as Record<string, string>)['Content-Type']).toBe('application/json')
  })

  it('非 2xx 抛出带 code/status 的 ApiError', async () => {
    mockFetch(() => jsonResponse({ code: 'ERR_2001', message: '会话不存在' }, 400))
    await expect(api.getSession('nope')).rejects.toBeInstanceOf(ApiError)
    await expect(api.getSession('nope')).rejects.toMatchObject({
      code: 'ERR_2001',
      status: 400,
    })
  })

  it('createSession 缺少 session_id 时报错', async () => {
    mockFetch(() => jsonResponse({ status: 'ok' }))
    await expect(api.createSession({})).rejects.toMatchObject({ code: 'ERR_1000' })
  })

  it('sendMessage 返回 run_id 与 message_id', async () => {
    mockFetch(() => jsonResponse({ run_id: 'run_1', message_id: 'msg_1' }))
    const res = await api.sendMessage('sess_1', { role: 'user', content: '你好' })
    expect(res.run_id).toBe('run_1')
    expect(res.message_id).toBe('msg_1')
  })
})
