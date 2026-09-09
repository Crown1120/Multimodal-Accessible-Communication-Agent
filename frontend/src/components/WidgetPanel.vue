<script setup lang="ts">
import { computed } from 'vue'
import { useSessionStore } from '@/stores/session'
import { widgetRegistry } from '@/widgets'

const store = useSessionStore()

// 精简展示：去掉「知识来源」等对用户无增益的内容卡
const visibleWidgets = computed(() =>
  store.widgets.filter((w) => w.widget_type !== 'knowledge_source'),
)

/** 已注册的 Widget 类型才渲染；未知类型给出友好提示，而不是把原始 JSON 抛给用户 */
function componentFor(widgetType: string) {
  return widgetRegistry[widgetType as keyof typeof widgetRegistry] ?? null
}
</script>

<template>
  <!-- 精简版：只渲染 Widget 内容卡，去掉「服务信息」标题框与「知识来源」 -->
  <section class="widget-panel" aria-label="服务信息">
    <template v-for="w in visibleWidgets" :key="w.widget_id">
      <component
        :is="componentFor(w.widget_type)"
        v-if="componentFor(w.widget_type)"
        class="widget-item"
        :payload="w.payload"
      />
      <p v-else class="widget-unknown" role="status">
        收到一种暂不支持的展示类型（{{ w.widget_type }}），请以数字人播报内容为准。
      </p>
    </template>
  </section>
</template>

<style scoped>
.widget-panel {
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-width: 0;
}

.widget-item {
  width: 100%;
}
.fallback {
  margin: 0;
  font-size: 0.8em;
  white-space: pre-wrap;
  word-break: break-all;
  color: var(--color-text-muted);
  background: var(--color-surface-2);
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
  padding: 10px;
}
</style>
