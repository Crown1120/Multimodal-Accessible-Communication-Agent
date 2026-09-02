<script setup lang="ts">
defineProps<{
  payload: Record<string, unknown>
}>()
</script>

<template>
  <div class="ks-widget">
    <div class="head">
      <span class="icon">📚</span>
      <span>知识来源</span>
    </div>
    <div class="conf" :class="{ low: !(payload.confident as boolean) }">
      {{ payload.confident as boolean ? '置信度：较高' : '置信度：较低，请核验' }}
    </div>
    <ul class="sources">
      <li v-for="(s, i) in ((payload.sources as Record<string, unknown>[]) ?? [])" :key="i">
        <span class="title">{{ s.title }}</span>
        <span class="src">来源：{{ s.source }}</span>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.ks-widget {
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
.conf {
  font-size: 0.85em;
  color: var(--color-accent);
  margin-bottom: 8px;
}
.conf.low {
  color: var(--color-warning);
}
.sources {
  margin: 0;
  padding-left: 18px;
}
.sources li {
  margin: 4px 0;
  font-size: 0.85em;
}
.title {
  font-weight: 600;
}
.src {
  display: block;
  color: var(--color-text-muted);
}
</style>
