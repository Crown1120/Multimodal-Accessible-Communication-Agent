<script setup lang="ts">
import { useToast } from '@/composables/useToast'

const { toasts, dismiss } = useToast()

const iconMap: Record<string, string> = {
  error: '⚠',
  warning: '⚠',
  info: 'ℹ',
  success: '✓',
}
</script>

<template>
  <Teleport to="body">
    <!-- role="status" 已隐含 aria-live="polite"；原先同时写 role="alert" 与
         aria-live="polite" 语义冲突（alert 隐含 assertive） -->
    <div class="toast-container" role="status" aria-live="polite">
      <TransitionGroup name="toast">
        <button
          v-for="t in toasts"
          :key="t.id"
          type="button"
          class="toast"
          :class="`toast-${t.type}`"
          :aria-label="`${t.message}（点击关闭）`"
          @click="dismiss(t.id)"
        >
          <span class="toast-icon" aria-hidden="true">{{ iconMap[t.type] }}</span>
          <span class="toast-message">{{ t.message }}</span>
        </button>
      </TransitionGroup>
    </div>
  </Teleport>
</template>

<style scoped>
.toast-container {
  position: fixed;
  top: 20px;
  right: 20px;
  z-index: 9999;
  display: flex;
  flex-direction: column;
  gap: 10px;
  max-width: 380px;
  pointer-events: none;
}

.toast {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 12px 16px;
  border-radius: 12px;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.15);
  cursor: pointer;
  pointer-events: auto;
  font-size: 14px;
  line-height: 1.5;
  font-family: inherit;
  text-align: left;
  animation: toast-in 0.3s ease;
}

.toast-icon {
  flex-shrink: 0;
  font-size: 16px;
  line-height: 1.4;
}

.toast-message {
  flex: 1;
  color: var(--color-text);
  word-break: break-word;
}

.toast-error {
  border-left: 4px solid #ef4444;
  background: #fef2f2;
}
.toast-error .toast-icon {
  color: #ef4444;
}

.toast-warning {
  border-left: 4px solid #f59e0b;
  background: #fffbeb;
}
.toast-warning .toast-icon {
  color: #f59e0b;
}

.toast-info {
  border-left: 4px solid #3b82f6;
  background: #eff6ff;
}
.toast-info .toast-icon {
  color: #3b82f6;
}

.toast-success {
  border-left: 4px solid #22c55e;
  background: #f0fdf4;
}
.toast-success .toast-icon {
  color: #22c55e;
}

/* 听障模式：高对比度 */
[data-mode='hearing'] .toast {
  background: #000;
  border-color: #ffd700;
  color: #fff;
}
[data-mode='hearing'] .toast-message {
  color: #fff;
}

/* 老年模式：更大字体 */
[data-mode='elderly'] .toast {
  font-size: 17px;
  padding: 14px 18px;
}

@keyframes toast-in {
  from {
    opacity: 0;
    transform: translateX(30px);
  }
  to {
    opacity: 1;
    transform: translateX(0);
  }
}

.toast-leave-active {
  transition: all 0.3s ease;
}
.toast-leave-to {
  opacity: 0;
  transform: translateX(30px);
}
</style>
