// Widget 统一注册：widget_type -> 组件

import { defineAsyncComponent } from 'vue'

import type { Component } from 'vue'

export const widgetRegistry: Record<string, Component> = {
  map_route: defineAsyncComponent(() => import('./MapRouteWidget.vue')),
  location: defineAsyncComponent(() => import('./LocationWidget.vue')),
  task_result: defineAsyncComponent(() => import('./TaskResultWidget.vue')),
  translation: defineAsyncComponent(() => import('./TranslationWidget.vue')),
}
