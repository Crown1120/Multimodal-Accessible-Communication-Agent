import { ref } from 'vue'

export interface ToastItem {
  id: number
  type: 'error' | 'warning' | 'info' | 'success'
  message: string
  duration: number
}

const toasts = ref<ToastItem[]>([])
let nextId = 1

function show(type: ToastItem['type'], message: string, duration = 4000) {
  const id = nextId++
  toasts.value.push({ id, type, message, duration })
  if (duration > 0) {
    setTimeout(() => dismiss(id), duration)
  }
  return id
}

function dismiss(id: number) {
  const idx = toasts.value.findIndex((t) => t.id === id)
  if (idx >= 0) toasts.value.splice(idx, 1)
}

export function useToast() {
  return {
    toasts,
    error: (msg: string, dur?: number) => show('error', msg, dur),
    warning: (msg: string, dur?: number) => show('warning', msg, dur),
    info: (msg: string, dur?: number) => show('info', msg, dur),
    success: (msg: string, dur?: number) => show('success', msg, dur),
    dismiss,
  }
}
