// 实时字幕组件测试：验证 P0 修复——字幕确实渲染到 DOM，且具备屏幕阅读器播报所需的 live region。
//
// 回归背景：store 一直在维护 transcript，但此前没有任何模板读取它，
// 听障用户既看不到字幕，屏幕阅读器也不会播报。

import { beforeEach, describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

import SubtitleBar from '@/components/SubtitleBar.vue'
import { useSessionStore } from '@/stores/session'

describe('SubtitleBar', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('无字幕时显示占位文案', () => {
    const wrapper = mount(SubtitleBar)
    expect(wrapper.text()).toContain('等待语音或回复')
  })

  it('渲染 store.transcript 且带 aria-live 区域', () => {
    const store = useSessionStore()
    store.transcript = '骨科在门诊二楼外科区域'
    store.transcriptSpeaker = 'assistant'

    const wrapper = mount(SubtitleBar)
    const live = wrapper.find('[role="status"]')

    expect(live.exists()).toBe(true)
    expect(live.attributes('aria-live')).toBe('polite')
    // 流式追加时只播报变化部分，避免整段重读
    expect(live.attributes('aria-atomic')).toBe('false')
    expect(live.text()).toContain('骨科在门诊二楼外科区域')
  })

  it('显示说话人标签', () => {
    const store = useSessionStore()
    store.transcript = '请到一楼服务台'
    store.transcriptSpeaker = 'staff'

    const wrapper = mount(SubtitleBar)
    expect(wrapper.text()).toContain('工作人员')
  })

  it('有字幕时激活态用于视觉提示', () => {
    const store = useSessionStore()
    store.transcript = '测试'
    const wrapper = mount(SubtitleBar)
    expect(wrapper.find('.subtitle-bar').classes()).toContain('active')
  })
})
