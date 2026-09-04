<script setup lang="ts">
import BIcon from '@/components/BIcon.vue'

defineProps<{
  payload: Record<string, unknown>
}>()
</script>

<template>
  <div class="location-widget">
    <div class="head">
      <span class="head-icon">
        <BIcon name="pin" :size="15" />
      </span>
      <span class="head-title">地点信息</span>
    </div>

    <div
      class="loc"
      v-for="(loc, i) in ((payload.locations as Record<string, unknown>[]) ?? [])"
      :key="i"
    >
      <div class="name">
        <span class="loc-pin"><BIcon name="pin" :size="13" /></span>
        {{ loc.name }}
      </div>
      <div class="meta">
        <span class="chip" v-if="loc.floor">楼层 {{ loc.floor }}</span>
        <span class="chip" v-if="loc.area">{{ loc.area }}</span>
        <span class="chip dir" v-if="loc.direction">{{ loc.direction }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.location-widget {
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
  padding: 12px;
  background: var(--color-surface);
  box-shadow: var(--shadow-xs);
  overflow: hidden;
  position: relative;
}
.location-widget::before {
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

.loc {
  padding: 9px 0;
  border-top: 1px solid var(--color-border);
}
.loc:first-of-type {
  border-top: none;
}
.name {
  display: flex;
  align-items: center;
  gap: 6px;
  font-weight: 600;
  font-size: 0.94em;
}
.loc-pin {
  color: var(--color-danger);
  display: inline-flex;
}
.meta {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 6px;
}
.chip {
  font-size: 0.76em;
  font-weight: 600;
  color: var(--color-text-muted);
  background: var(--color-surface-2);
  border: 1px solid var(--color-border);
  padding: 2px 9px;
  border-radius: var(--radius-pill);
}
.chip.dir {
  color: var(--color-accent);
  background: var(--color-accent-soft);
  border-color: transparent;
}
</style>
