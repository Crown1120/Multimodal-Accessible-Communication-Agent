<script setup lang="ts">
defineProps<{
  payload: Record<string, unknown>
}>()
</script>

<template>
  <div class="translation-widget">
    <div class="head">
      <span class="icon">🌐</span>
      <span>中英翻译</span>
    </div>
    <div class="pair">
      <div class="row">
        <span class="lang">中文</span>
        <span class="text">{{ payload.source as string }}</span>
      </div>
      <div class="row">
        <span class="lang">English</span>
        <span class="text en">{{ payload.result as string }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.translation-widget {
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
.pair {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.row {
  display: flex;
  align-items: baseline;
  gap: 8px;
}
.lang {
  font-size: 0.75em;
  color: var(--color-text-muted);
  min-width: 48px;
  flex-shrink: 0;
}
.text {
  flex: 1;
}
.text.en {
  font-style: italic;
}
</style>
