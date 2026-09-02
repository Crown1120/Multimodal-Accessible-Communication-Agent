<script setup lang="ts">
import { ref } from 'vue'
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
      :aria-expanded="open"
      aria-label="无障碍偏好设置"
      @click="toggle"
    >
      ⚙ 偏好
    </button>

    <Transition name="slide">
      <div v-if="open" class="pref-body" role="dialog" aria-label="无障碍偏好">
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
            {{ store.highContrast ? '开' : '关' }}
          </button>
        </div>

        <!-- 清除偏好 -->
        <button class="pref-clear" @click="store.clearPreferences()">
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
  font-size: 0.9em;
  padding: 6px 12px;
}

.pref-body {
  position: absolute;
  top: 100%;
  right: 0;
  margin-top: 8px;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
  box-shadow: var(--shadow);
  padding: 16px;
  min-width: 240px;
  z-index: 100;
  display: flex;
  flex-direction: column;
  gap: 14px;
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
}

.pref-btns {
  display: flex;
  gap: 6px;
}

.pref-btns button {
  padding: 4px 12px;
  font-size: 0.85em;
}

.toggle-btn {
  min-width: 48px;
  font-weight: 500;
}

.toggle-btn.on {
  background: var(--color-primary);
  color: #fff;
  border-color: var(--color-primary);
}

.pref-clear {
  margin-top: 4px;
  color: var(--color-danger);
  border-color: var(--color-danger);
  font-size: 0.85em;
}

.pref-clear:hover {
  background: var(--color-danger);
  color: #fff;
}

.slide-enter-active,
.slide-leave-active {
  transition: all var(--transition-fast);
}

.slide-enter-from,
.slide-leave-to {
  opacity: 0;
  transform: translateY(-8px);
}
</style>
