<script setup lang="ts">
import BIcon from '@/components/BIcon.vue'

defineProps<{
  payload: Record<string, unknown>
}>()
</script>

<template>
  <div class="ks-widget">
    <div class="head">
      <span class="head-icon">
        <BIcon name="book" :size="15" />
      </span>
      <span class="head-title">知识来源</span>
    </div>

    <div class="conf" :class="{ low: !(payload.confident as boolean) }">
      <BIcon :name="payload.confident ? 'check' : 'alert'" :size="14" />
      {{ payload.confident ? '置信度：较高' : '置信度：较低，请核验' }}
    </div>

    <ul class="sources">
      <li v-for="(s, i) in ((payload.sources as Record<string, unknown>[]) ?? [])" :key="i">
        <span class="title">{{ s.title }}</span>
        <span class="src">
          <BIcon name="pin" :size="11" />
          {{ s.source }}
        </span>
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
  box-shadow: var(--shadow-xs);
  overflow: hidden;
  position: relative;
}
.ks-widget::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 3px;
  background: var(--color-primary-gradient);
}

.head {
  display: flex;
  align-items: center;
  gap: 7px;
  font-weight: 700;
  margin-bottom: 8px;
  color: var(--color-text);
  font-size: 0.94em;
}
.head-icon {
  width: 26px;
  height: 26px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--color-primary-soft);
  color: var(--color-primary);
}

.conf {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 0.82em;
  font-weight: 600;
  color: var(--color-success);
  background: var(--color-success-soft);
  padding: 4px 10px;
  border-radius: var(--radius-pill);
  margin-bottom: 9px;
}
.conf.low {
  color: var(--color-warning);
  background: var(--color-warning-soft);
}

.sources {
  margin: 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 7px;
}
.sources li {
  padding: 8px 10px;
  background: var(--color-surface-2);
  border: 1px solid var(--color-border);
  border-radius: 10px;
  font-size: 0.84em;
}
.title {
  display: block;
  font-weight: 600;
  margin-bottom: 2px;
}
.src {
  display: flex;
  align-items: center;
  gap: 4px;
  color: var(--color-text-muted);
  font-size: 0.82em;
}
.src .b-icon {
  color: var(--color-accent);
}
</style>
