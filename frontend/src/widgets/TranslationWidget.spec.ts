// 翻译 Widget 回归测试：语言标签必须跟随 payload 的 source_lang / target_lang。
//
// 回归背景：模板把两行写死成「中文 / English」，当用户要求「翻译成中文」
// （英→中）时，译文会被标成英文，原文被标成中文，完全误导。

import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'

import TranslationWidget from '@/widgets/TranslationWidget.vue'

function mountWith(payload: Record<string, unknown>) {
  return mount(TranslationWidget, { props: { payload } })
}

describe('TranslationWidget', () => {
  it('中译英时标签为 中文 / English', () => {
    const wrapper = mountWith({
      source: '骨科在哪里',
      result: 'Where is the orthopedics department',
      source_lang: 'zh',
      target_lang: 'en',
    })
    const labels = wrapper.findAll('.lang').map((n) => n.text())
    expect(labels).toEqual(['中文', 'English'])
  })

  it('英译中时标签顺序随之反转', () => {
    const wrapper = mountWith({
      source: 'Where is the pharmacy',
      result: '药房在哪里',
      source_lang: 'en',
      target_lang: 'zh',
    })
    const labels = wrapper.findAll('.lang').map((n) => n.text())
    expect(labels).toEqual(['English', '中文'])
  })

  it('缺少语言字段时回退为 中文 / English', () => {
    const wrapper = mountWith({ source: 'a', result: 'b' })
    const labels = wrapper.findAll('.lang').map((n) => n.text())
    expect(labels).toEqual(['中文', 'English'])
  })

  it('渲染原文与译文', () => {
    const wrapper = mountWith({
      source: '请问挂号在哪里',
      result: 'Excuse me, where is registration',
      source_lang: 'zh',
      target_lang: 'en',
    })
    expect(wrapper.text()).toContain('请问挂号在哪里')
    expect(wrapper.text()).toContain('Excuse me, where is registration')
  })
})
