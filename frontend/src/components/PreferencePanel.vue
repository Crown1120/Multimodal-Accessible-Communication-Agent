<script setup lang="ts">
import { ref } from 'vue'

import BIcon from '@/components/BIcon.vue'
import { useSessionStore } from '@/stores/session'

const store = useSessionStore()
const open = ref(false)

const fontSizes = [
  { value: 'small' as const, label: '小' },
  { value: 'medium' as const, label: '中' },
  { value: 'large' as const, label: '大' },
]

const speechRates = [
  { value: 'normal' as const, label: '正常' },
  { value: 'slow' as const, label: '慢速' },
]

function toggle() {
  open.value = !open.value
}
</script>

<template>
  <div class="pref-panel">
    <button
      class="pref-toggle"
      :class="{ on: open }"
      :aria-expanded="open"
      aria-label="无障碍偏好设置"
      @click="toggle"
    >
      <BIcon name="settings" :size="16" />
      <span>偏好</span>
    </button>

    <Transition name="slide">
      <div v-if="open" class="pref-body" role="dialog" aria-label="无障碍偏好">
        <div class="pref-title">无障碍偏好</div>

        <!-- 字号 -->
        <div class="pref-row">
          <span class="pref-label">字号</span>
          <div class="pref-btns" role="group" aria-label="字号选择">
            <button
              v-for="f in fontSizes"
              :key="f.value"
              :class="{ primary: store.fontSize === f.value }"
              :aria-pressed="store.fontSize === f.value"
              @click="store.setFontSize(f.value)"
            >
              {{ f.label }}
            </button>
          </div>
        </div>

        <!-- 语速 -->
        <div class="pref-row">
          <span class="pref-label">语速</span>
          <div class="pref-btns" role="group" aria-label="语速选择">
            <button
              v-for="r in speechRates"
              :key="r.value"
              :class="{ primary: store.speechRate === r.value }"
              :aria-pressed="store.speechRate === r.value"
              @click="store.setSpeechRate(r.value)"
            >
              {{ r.label }}
            </button>
          </div>
        </div>

        <!-- 高对比度 -->
        <div class="pref-row">
          <span class="pref-label">高对比度</span>
          <button
            class="toggle-btn"
            :class="{ on: store.highContrast }"
            :aria-pressed="store.highContrast"
            @click="store.setHighContrast(!store.highContrast)"
          >
            <span class="toggle-knob"></span>
          </button>
        </div>

        <!-- 清除偏好 -->
        <button class="pref-clear" @click="store.clearPreferences()">
          <BIcon name="trash" :size="14" />
          清除偏好
        </button>
      </div>
    </Transition>
  </div>
</template>

<style scoped>
.pref-panel {
  position: relative;
}

.pref-toggle {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 0.88em;
  padding: 7px 13px;
  border-radius: var(--radius-pill);
  border: 1px solid var(--color-border);
  background: var(--color-surface);
  color: var(--color-text-muted);
}
.pref-toggle:hover:not(:disabled) {
  color: var(--color-primary);
  border-color: var(--color-primary);
}
.pref-toggle.on {
  background: var(--color-primary-soft);
  color: var(--color-primary);
  border-color: var(--color-primary);
}

.pref-body {
  position: absolute;
  top: calc(100% + 10px);
  right: 0;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-lg);
  padding: 16px;
  min-width: 260px;
  z-index: 100;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.pref-title {
  font-weight: 700;
  font-size: 0.98em;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--color-border);
}

.pref-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.pref-label {
  font-weight: 500;
  white-space: nowrap;
  font-size: 0.92em;
}

.pref-btns {
  display: flex;
  gap: 6px;
}

.pref-btns button {
  padding: 4px 13px;
  font-size: 0.85em;
  border-radius: var(--radius-sm);
}

/* 开关 */
.toggle-btn {
  position: relative;
  width: 46px;
  height: 26px;
  border-radius: var(--radius-pill);
  border: 1.5px solid var(--color-border-strong);
  background: var(--color-surface-2);
  padding: 0;
  transition:
    background var(--transition-fast),
    border-color var(--transition-fast);
}
.toggle-knob {
  position: absolute;
  top: 2px;
  left: 2px;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: #fff;
  box-shadow: var(--shadow-sm);
  transition: transform var(--transition);
}
.toggle-btn.on {
  background: var(--color-primary-gradient);
  border-color: transparent;
}
.toggle-btn.on .toggle-knob {
  transform: translateX(20px);
}

.pref-clear {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  margin-top: 4px;
  color: var(--color-danger);
  border-color: var(--color-danger);
  border-radius: var(--radius-sm);
  font-size: 0.86em;
}
.pref-clear:hover {
  background: var(--color-danger);
  color: #fff;
}

.slide-enter-active,
.slide-leave-active {
  transition: all var(--transition);
}
.slide-enter-from,
.slide-leave-to {
  opacity: 0;
  transform: translateY(-8px) scale(0.98);
}
</style>
