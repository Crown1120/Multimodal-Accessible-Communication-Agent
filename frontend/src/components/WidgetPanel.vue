<script setup lang="ts">
import { computed } from 'vue'
import { useSessionStore } from '@/stores/session'
import { widgetRegistry } from '@/widgets'

const store = useSessionStore()

// 精简展示：去掉「知识来源」等对用户无增益的内容卡
const visibleWidgets = computed(() =>
  store.widgets.filter((w) => w.widget_type !== 'knowledge_source'),
)
</script>

<template>
  <!-- 精简版：只渲染 Widget 内容卡，去掉「服务信息」标题框与「知识来源」 -->
  <section class="widget-panel" aria-label="服务信息">
    <component
      v-for="w in visibleWidgets"
      :key="w.widget_id"
      :is="widgetRegistry[w.widget_type] ?? 'div'"
      class="widget-item"
      :payload="w.payload"
    >
      <template #default>
        <pre class="fallback">{{ JSON.stringify(w.payload, null, 2) }}</pre>
      </template>
    </component>
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
