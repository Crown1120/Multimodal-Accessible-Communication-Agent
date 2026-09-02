<script setup lang="ts">
defineProps<{
  payload: Record<string, unknown>
}>()
</script>

<template>
  <div class="map-route-widget">
    <div class="head">
      <span class="icon">🗺️</span>
      <span>路线规划</span>
    </div>
    <div class="endpoints">
      <span class="from">起点：{{ payload.origin }}</span>
      <span class="arrow">→</span>
      <span class="to">终点：{{ payload.destination }}</span>
    </div>
    <ol class="steps">
      <li v-for="(s, i) in (payload.steps as string[])" :key="i">{{ s }}</li>
    </ol>
    <div class="floor" v-if="payload.floor">所在楼层：{{ payload.floor }} 楼</div>
  </div>
</template>

<style scoped>
.map-route-widget {
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
  padding: 12px;
  background: var(--color-surface);
}
.head {
  display: flex;
  align-items: center;
  gap: 6px;
  font-weight: 600;
  margin-bottom: 8px;
  color: var(--color-primary);
}
.endpoints {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 0.9em;
  margin-bottom: 8px;
  color: var(--color-text-muted);
}
.arrow {
  color: var(--color-primary);
}
.steps {
  margin: 0 0 8px;
  padding-left: 20px;
}
.steps li {
  margin: 4px 0;
}
.floor {
  font-size: 0.85em;
  color: var(--color-text-muted);
}
</style>
