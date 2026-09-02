<script setup lang="ts">
defineProps<{
  payload: Record<string, unknown>
}>()
</script>

<template>
  <div class="location-widget">
    <div class="head">
      <span class="icon">📍</span>
      <span>地点信息</span>
    </div>
    <div
      class="loc"
      v-for="(loc, i) in ((payload.locations as Record<string, unknown>[]) ?? [])"
      :key="i"
    >
      <div class="name">{{ loc.name }}</div>
      <div class="meta">{{ loc.floor }} 楼 · {{ loc.area }} · {{ loc.direction }}</div>
    </div>
  </div>
</template>

<style scoped>
.location-widget {
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
.loc {
  padding: 8px 0;
  border-top: 1px solid var(--color-border);
}
.loc:first-of-type {
  border-top: none;
}
.name {
  font-weight: 600;
}
.meta {
  font-size: 0.85em;
  color: var(--color-text-muted);
  margin-top: 2px;
}
</style>
