<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { useSessionStore } from '@/stores/session'

const store = useSessionStore()
const showGuide = ref(false)
const step = ref(0)
const nextBtnRef = ref<HTMLButtonElement | null>(null)

const GUIDE_KEY = 'bridge_elderly_guide_shown'

const steps = [
  {
    title: '欢迎使用 Bridge 无障碍沟通',
    desc: '这是为您设计的老年模式，字体更大、操作更简单。',
  },
  {
    title: '在这里输入您的问题',
    desc: '点击下方输入框，输入您想问的问题，然后点击发送按钮。',
  },
  {
    title: '也可以直接说话',
    desc: '点击麦克风按钮，直接说出您的问题，系统会自动识别。',
  },
  {
    title: '数字人会回答您',
    desc: '屏幕中的数字人会用语音和文字回答您的问题，请放心使用。',
  },
]

onMounted(() => {
  checkGuide()
  window.addEventListener('keydown', onKeydown)
})

onUnmounted(() => {
  window.removeEventListener('keydown', onKeydown)
})

watch(
  () => store.mode,
  (mode) => {
    if (mode === 'elderly') checkGuide()
  },
)

watch(showGuide, async (visible) => {
  if (visible) {
    // 打开后把焦点移入弹层，键盘用户不会迷失在原页面
    await nextTick()
    nextBtnRef.value?.focus()
  }
})

// Esc 关闭弹层（无障碍要求）
function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape' && showGuide.value) {
    e.preventDefault()
    skip()
  }
}

function checkGuide() {
  if (store.mode !== 'elderly') return
  const shown = localStorage.getItem(GUIDE_KEY)
  if (!shown) {
    showGuide.value = true
    step.value = 0
  }
}

function next() {
  if (step.value < steps.length - 1) {
    step.value++
  } else {
    finish()
  }
}

function finish() {
  showGuide.value = false
  localStorage.setItem(GUIDE_KEY, '1')
}

function skip() {
  finish()
}
</script>

<template>
  <Teleport to="body">
    <Transition name="guide-fade">
      <div v-if="showGuide" class="guide-overlay" @click.self="skip">
        <div
          class="guide-card"
          role="dialog"
          aria-modal="true"
          aria-labelledby="elderly-guide-title"
          aria-describedby="elderly-guide-desc"
        >
          <div class="guide-step">{{ step + 1 }} / {{ steps.length }}</div>
          <h3 id="elderly-guide-title" class="guide-title">{{ steps[step].title }}</h3>
          <p id="elderly-guide-desc" class="guide-desc">{{ steps[step].desc }}</p>
          <div class="guide-actions">
            <button class="guide-skip" type="button" @click="skip">跳过</button>
            <button ref="nextBtnRef" class="guide-next" type="button" @click="next">
              {{ step < steps.length - 1 ? '下一步' : '开始使用' }}
            </button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.guide-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.6);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 10000;
  padding: 20px;
}

.guide-card {
  background: #fff;
  border-radius: 20px;
  padding: 32px;
  max-width: 440px;
  width: 100%;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
  text-align: center;
}

.guide-step {
  font-size: 15px;
  color: #888;
  margin-bottom: 12px;
}

.guide-title {
  font-size: 24px;
  font-weight: 700;
  color: #1a1a2e;
  margin: 0 0 16px;
}

.guide-desc {
  font-size: 18px;
  line-height: 1.7;
  color: #444;
  margin: 0 0 28px;
}

.guide-actions {
  display: flex;
  gap: 12px;
  justify-content: center;
}

.guide-skip {
  padding: 12px 28px;
  border-radius: 12px;
  border: 2px solid #ddd;
  background: #fff;
  color: #666;
  font-size: 17px;
  cursor: pointer;
}

.guide-next {
  padding: 12px 28px;
  border-radius: 12px;
  border: none;
  background: linear-gradient(135deg, #4f6ef7, #6c5ce7);
  color: #fff;
  font-size: 17px;
  font-weight: 600;
  cursor: pointer;
  box-shadow: 0 4px 12px rgba(79, 110, 247, 0.4);
}

.guide-fade-enter-active,
.guide-fade-leave-active {
  transition: opacity 0.3s ease;
}
.guide-fade-enter-from,
.guide-fade-leave-to {
  opacity: 0;
}
</style>
