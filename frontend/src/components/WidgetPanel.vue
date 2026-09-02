<script setup lang="ts">
import { useSessionStore } from '@/stores/session'
import { widgetRegistry } from '@/widgets'

const store = useSessionStore()
</script>

<template>
  <section class="widget-panel" aria-label="Widget 区">
    <div class="empty" v-if="store.widgets.length === 0">地图、路线与服务信息将在此展示</div>
    <component
      v-for="w in store.widgets"
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
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  overflow-y: auto;
}
.empty {
  color: var(--color-text-muted);
  text-align: center;
  margin-top: 24px;
}
.widget-item {
  width: 100%;
}
.fallback {
  margin: 0;
  font-size: 0.82em;
  white-space: pre-wrap;
  word-break: break-all;
  color: var(--color-text-muted);
}
</style>
