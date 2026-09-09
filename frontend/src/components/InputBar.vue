<script setup lang="ts">
import { ref, computed, onUnmounted } from 'vue'

import BIcon from '@/components/BIcon.vue'
import { useSessionStore } from '@/stores/session'

const store = useSessionStore()
const text = ref('')
const micError = ref('')
const sendError = ref('')
const lastContent = ref('')

// 高频问题快捷按钮：按场景区分（此前只有医院话术，政务场景会给出无关问题）
type SceneQuickConfig = {
  recommendations: Record<string, string[]>
  defaults: string[]
  elderlyDefaults: string[]
}

const HOSPITAL_QUICK: SceneQuickConfig = {
  recommendations: {
    骨科: ['骨科挂号流程', '骨科医生排班', '骨科在几楼', '骨科急诊'],
    内科: ['内科挂号流程', '内科医生排班', '内科在几楼', '心内科在哪'],
    外科: ['外科挂号流程', '外科医生排班', '外科在几楼', '普外科在哪'],
    急诊: ['急诊在哪', '急诊流程', '急诊电话', '急诊挂号'],
    挂号: ['挂号流程', '挂号费用', '线上挂号', '预约挂号'],
    缴费: ['缴费方式', '缴费窗口在哪', '医保报销', '自助缴费'],
    交费: ['缴费方式', '缴费窗口在哪', '医保报销', '自助缴费'],
    取药: ['取药窗口在哪', '取药流程', '药品查询', '中药房在哪'],
    拿药: ['取药窗口在哪', '取药流程', '药品查询', '中药房在哪'],
    洗手间: ['洗手间位置', '无障碍洗手间', '洗手间在几楼'],
    厕所: ['洗手间位置', '无障碍洗手间', '洗手间在几楼'],
    电梯: ['电梯位置', '无障碍电梯', '电梯在几楼'],
    儿科: ['儿科挂号', '儿科医生排班', '儿科在几楼', '儿科急诊'],
    妇产: ['妇产科挂号', '妇产科医生', '妇产科在几楼', '产科门诊'],
    眼科: ['眼科挂号', '眼科医生', '眼科在几楼', '视力检查'],
    口腔: ['口腔科挂号', '口腔科医生', '口腔科在几楼', '拔牙流程'],
    牙科: ['口腔科挂号', '口腔科医生', '口腔科在几楼', '拔牙流程'],
    体检: ['体检流程', '体检中心在哪', '体检预约', '体检费用'],
    住院: ['住院流程', '住院部在哪', '陪护规定', '探视时间'],
    化验: ['化验室在哪', '抽血流程', '化验单查询', '空腹要求'],
    检查: ['检查室在哪', 'CT室在哪', 'B超室在哪', '核磁共振预约'],
  },
  defaults: ['挂号在哪', '洗手间在哪', '急诊怎么走', '骨科在哪', '取药处', '缴费'],
  elderlyDefaults: ['挂号在哪', '洗手间在哪', '急诊怎么走', '取药处'],
}

const GOVERNMENT_QUICK: SceneQuickConfig = {
  recommendations: {
    身份证: ['身份证办理流程', '身份证需要什么材料', '身份证多久能拿到', '临时身份证'],
    社保: ['社保卡申领', '社保转移流程', '社保缴费查询', '医保报销'],
    医保: ['医保报销流程', '医保卡怎么用', '异地就医备案', '医保缴费'],
    公积金: ['公积金提取', '公积金贷款', '公积金查询', '公积金转移'],
    户口: ['户口迁移流程', '落户需要什么材料', '新生儿上户口', '户口本补办'],
    户籍: ['户籍窗口在哪', '户籍证明怎么开', '户籍迁移材料', '户口本补办'],
    不动产: ['不动产登记流程', '房产证办理', '不动产窗口在哪', '过户需要什么材料'],
    营业执照: ['营业执照办理', '营业执照变更', '个体户注册', '营业执照窗口'],
    居住证: ['居住证办理流程', '居住证需要什么材料', '居住证续期'],
    护照: ['护照办理流程', '护照需要什么材料', '出入境窗口在哪', '港澳通行证'],
    结婚证: ['结婚登记流程', '结婚需要什么材料', '离婚登记', '婚姻登记窗口'],
    洗手间: ['洗手间位置', '无障碍洗手间', '洗手间在几楼'],
    电梯: ['电梯位置', '无障碍电梯', '电梯在几楼'],
    叫号: ['怎么取号', '叫号规则', '优先叫号', '过号怎么办'],
  },
  defaults: ['身份证怎么办', '社保卡申领', '公积金提取', '洗手间在哪', '叫号在哪取', '导办台在哪'],
  elderlyDefaults: ['身份证怎么办', '洗手间在哪', '导办台在哪', '叫号在哪取'],
}

const quickConfig = computed(() =>
  store.scene === 'government' ? GOVERNMENT_QUICK : HOSPITAL_QUICK,
)

// 获取最近的用户消息文本
const lastUserMessage = computed(() => {
  const msgs = store.messages
  for (let i = msgs.length - 1; i >= 0; i--) {
    if (msgs[i].role === 'user') return msgs[i].content
  }
  return ''
})

const quickQuestions = computed(() => {
  const config = quickConfig.value
  // 老年模式：固定 4 个常用按钮
  if (store.mode === 'elderly') {
    return config.elderlyDefaults
  }
  // 动态推荐：根据最近用户消息的关键词匹配
  const lastMsg = lastUserMessage.value
  if (lastMsg) {
    for (const [keyword, recommendations] of Object.entries(config.recommendations)) {
      if (lastMsg.includes(keyword)) {
        return recommendations.slice(0, 4)
      }
    }
  }
  // 默认快捷按钮
  return config.defaults
})

async function send(content?: string) {
  const msg = (content ?? text.value).trim()
  if (!msg || !store.sessionId || store.sending) return
  if (content === undefined) text.value = ''
  sendError.value = ''
  lastContent.value = msg
  try {
    await store.sendMessage(msg)
  } catch (error) {
    const errMsg = error instanceof Error ? error.message : '发送失败，请稍后重试'
    sendError.value = errMsg
    store.lastError = errMsg
  }
}

function retrySend() {
  if (lastContent.value) send(lastContent.value)
}

function repeatLast() {
  if (store.speakingText) {
    store.speak(store.speakingText)
  }
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    send()
  }
}

// ---- 录音上传 + 后端 ASR（MediaRecorder）----
const mediaRecorder = ref<MediaRecorder | null>(null)
const mediaStream = ref<MediaStream | null>(null)
const chunks = ref<Blob[]>([])

function pickMime(): string {
  const candidates = ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus', 'audio/mp4']
  for (const m of candidates) {
    if (MediaRecorder.isTypeSupported(m)) return m
  }
  return ''
}

/** 释放麦克风轨道；不释放会一直保持录音指示灯与占用设备 */
function releaseStream() {
  mediaStream.value?.getTracks().forEach((t) => t.stop())
  mediaStream.value = null
}

async function startRecording() {
  if (!store.sessionId || store.recording) return
  micError.value = ''
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    mediaStream.value = stream
    let recorder: MediaRecorder
    try {
      const mime = pickMime()
      recorder = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined)
      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunks.value.push(e.data)
      }
      recorder.onstop = async () => {
        const audioBlob = new Blob(chunks.value, { type: mime || 'audio/webm' })
        releaseStream()
        await store.uploadAudio(audioBlob)
      }
      recorder.start()
      mediaRecorder.value = recorder
      store.recording = true
    } catch (e) {
      // 创建/启动失败时必须立刻释放麦克风，否则录音指示灯会一直亮着
      releaseStream()
      throw e
    }
    chunks.value = []
  } catch {
    micError.value = '无法访问麦克风，请检查浏览器权限或使用文字输入'
    store.recording = false
  }
}

function stopRecording() {
  if (mediaRecorder.value && mediaRecorder.value.state === 'recording') {
    mediaRecorder.value.stop()
  } else {
    // 没有活动录音也要确保设备被释放
    releaseStream()
  }
  store.recording = false
}

function toggleMic() {
  if (store.recording) stopRecording()
  else startRecording()
}

onUnmounted(() => {
  // 组件卸载时停止录音并释放麦克风，避免后台继续占用设备
  if (mediaRecorder.value?.state === 'recording') {
    mediaRecorder.value.stop()
  }
  mediaRecorder.value = null
  releaseStream()
})

// 图片上传（报告解读）
const imageInputRef = ref<HTMLInputElement | null>(null)
const imageAnalyzing = ref(false)
const imageError = ref('')

function triggerImageUpload() {
  imageInputRef.value?.click()
}

async function onImageSelected(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file || !store.sessionId) return
  imageError.value = ''
  imageAnalyzing.value = true
  try {
    const result = await api.analyzeImage(store.sessionId, file)
    // 将解读结果作为助手消息发送
    await store.send(result.analysis)
  } catch (err) {
    imageError.value = err instanceof Error ? err.message : '图片解读失败，请重试'
  } finally {
    imageAnalyzing.value = false
    if (imageInputRef.value) imageInputRef.value.value = ''
  }
}

const waveBars = [0.9, 0.55, 1, 0.7, 0.45, 0.85, 0.6, 0.95, 0.5, 0.75]
</script>

<template>
  <section class="input-bar" aria-label="输入区">
    <!-- 常用问题快捷按钮 -->
    <div v-if="store.sessionId" class="quick-questions">
      <button
        v-for="q in quickQuestions"
        :key="q"
        class="quick-btn"
        :disabled="store.sending"
        @click="send(q)"
      >
        {{ q }}
      </button>
      <button
        v-if="store.mode === 'elderly' && store.speakingText"
        class="quick-btn repeat-btn"
        :disabled="store.sending"
        @click="repeatLast"
      >
        重复一遍
      </button>
    </div>

    <div class="field" :class="{ 'is-sending': store.sending }">
      <textarea
        v-model="text"
        :placeholder="
          store.sessionId ? (store.sending ? '回复中…' : '输入消息，回车发送') : '请先开始会话'
        "
        rows="1"
        :maxlength="store.maxMessageLength"
        :disabled="!store.sessionId || store.sending"
        @keydown="onKeydown"
      ></textarea>
      <!-- 说话按钮：录音上传 + 后端 ASR -->
      <button
        class="mic-btn"
        :class="{ recording: store.recording }"
        :disabled="!store.sessionId || store.sending"
        :aria-pressed="store.recording"
        :title="store.recording ? '停止录音' : '开始说话'"
        @click="toggleMic"
      >
        <span v-if="store.recording" class="mic-wave" aria-hidden="true">
          <i v-for="(h, i) in waveBars" :key="i" :style="{ height: h * 100 + '%' }"></i>
        </span>
        <BIcon v-else name="mic" :size="18" />
      </button>
      <!-- 图片上传按钮：报告解读 -->
      <input
        ref="imageInputRef"
        type="file"
        accept="image/*"
        capture="environment"
        class="image-input"
        aria-label="上传检查报告图片"
        @change="onImageSelected"
      />
      <button
        class="image-btn"
        :class="{ analyzing: imageAnalyzing }"
        :disabled="!store.sessionId || store.sending || imageAnalyzing"
        aria-label="上传检查报告图片进行AI解读"
        title="上传报告图片"
        @click="triggerImageUpload"
      >
        <span v-if="imageAnalyzing" class="spinner" aria-label="解读中"></span>
        <BIcon v-else name="image" :size="18" />
      </button>
      <button
        class="send"
        :disabled="!text.trim() || !store.sessionId || store.sending"
        aria-label="发送消息"
        title="发送 (Enter)"
        @click="send()"
      >
        <BIcon v-if="!store.sending" name="send" :size="17" />
        <span v-else class="spinner" aria-label="发送中"></span>
      </button>
    </div>
    <div v-if="micError" class="mic-error" role="alert">{{ micError }}</div>
    <div v-if="imageError" class="mic-error" role="alert">{{ imageError }}</div>
    <div v-if="sendError" class="send-error" role="alert">
      <span>{{ sendError }}</span>
      <button class="retry-btn" @click="retrySend">重试</button>
    </div>
  </section>
</template>

<style scoped>
.input-bar {
  flex: 1;
  min-width: 0;
  padding: 12px 14px 14px;
  background: var(--color-surface);
}

/* 常用问题快捷按钮 */
.quick-questions {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 10px;
}
.quick-btn {
  padding: 5px 12px;
  border-radius: 16px;
  border: 1px solid var(--color-border);
  background: var(--color-surface-2);
  color: var(--color-text-secondary);
  font-size: 13px;
  cursor: pointer;
  transition: all var(--transition-fast);
  white-space: nowrap;
}
.quick-btn:hover:not(:disabled) {
  border-color: var(--color-primary);
  color: var(--color-primary);
  background: var(--color-primary-soft);
}

.repeat-btn {
  border-color: var(--color-success);
  color: var(--color-success);
}

.repeat-btn:hover:not(:disabled) {
  border-color: var(--color-success);
  background: var(--color-success);
  color: #fff;
}
.quick-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
[data-mode='elderly'] .quick-btn {
  font-size: 16px;
  padding: 7px 16px;
}
[data-mode='hearing'] .quick-btn {
  border-width: 2px;
}

.field {
  display: flex;
  align-items: flex-end;
  gap: 8px;
  background: var(--color-surface-2);
  border: 1.5px solid var(--color-border);
  border-radius: var(--radius);
  padding: 8px 8px 8px 14px;
  transition:
    border-color var(--transition-fast),
    box-shadow var(--transition-fast);
}
.field:focus-within {
  border-color: var(--color-primary);
  box-shadow: 0 0 0 3px var(--color-primary-soft);
  background: var(--color-surface);
}
.field.is-sending {
  opacity: 0.7;
}

textarea {
  flex: 1;
  resize: none;
  border: none;
  background: transparent;
  outline: none;
  color: var(--color-text);
  line-height: 1.5;
  padding: 6px 0;
  max-height: 120px;
}
textarea::placeholder {
  color: var(--color-text-faint);
}
textarea:disabled {
  cursor: not-allowed;
}

.mic-btn {
  width: 40px;
  height: 40px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--color-surface);
  color: var(--color-primary);
  border: 1.5px solid var(--color-border);
  flex-shrink: 0;
  transition: all var(--transition-fast);
}
.mic-btn:hover:not(:disabled) {
  border-color: var(--color-primary);
  background: var(--color-primary-soft);
}
.mic-btn.recording {
  background: var(--color-danger);
  color: #fff;
  border-color: var(--color-danger);
  animation: recordPulse 1.4s ease-in-out infinite;
}
@keyframes recordPulse {
  0%, 100% { box-shadow: 0 0 0 0 rgba(229, 72, 77, 0.45); }
  50% { box-shadow: 0 0 0 10px rgba(229, 72, 77, 0); }
}
.mic-wave {
  display: flex;
  align-items: center;
  gap: 2px;
  height: 18px;
}
.mic-wave i {
  display: block;
  width: 3px;
  border-radius: 2px;
  background: currentColor;
  animation: micWave 0.9s ease-in-out infinite;
}
.mic-wave i:nth-child(2n) { animation-delay: 0.15s; }
.mic-wave i:nth-child(3n) { animation-delay: 0.3s; }
@keyframes micWave {
  0%, 100% { transform: scaleY(0.35); }
  50% { transform: scaleY(1); }
}
.mic-error {
  color: var(--color-danger);
  font-size: 0.82em;
  margin-top: 6px;
  text-align: center;
}

.send-error {
  margin-top: 6px;
  font-size: 0.82em;
  color: var(--color-danger);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.retry-btn {
  padding: 2px 10px;
  font-size: 0.82em;
  border: 1px solid var(--color-danger);
  border-radius: 4px;
  background: transparent;
  color: var(--color-danger);
  cursor: pointer;
  flex-shrink: 0;
}

.retry-btn:hover {
  background: var(--color-danger);
  color: #fff;
}

.send {
  width: 40px;
  height: 40px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--color-primary-gradient);
  color: #fff;
  border: none;
  box-shadow: var(--shadow-primary);
  flex-shrink: 0;
}
.send:hover:not(:disabled) {
  color: #fff;
  filter: brightness(1.08);
  transform: translateY(-1px);
}
.send:active:not(:disabled) {
  transform: translateY(0);
}
[data-mode='hearing'] .send {
  color: #000;
}

/* 发送中加载动画 */
.spinner {
  width: 18px;
  height: 18px;
  border: 2.5px solid rgba(255, 255, 255, 0.3);
  border-top-color: #fff;
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
}
[data-mode='hearing'] .spinner {
  border-color: rgba(0, 0, 0, 0.3);
  border-top-color: #000;
}
@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
