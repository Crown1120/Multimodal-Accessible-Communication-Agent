import { fileURLToPath, URL } from 'node:url'
import vue from '@vitejs/plugin-vue'
import { defineConfig, loadEnv } from 'vite'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const backendUrl = env.VITE_BACKEND_URL || 'http://localhost:8000'

  return {
    plugins: [vue()],
    resolve: {
      alias: {
        '@': fileURLToPath(new URL('./src', import.meta.url)),
      },
    },
    server: {
      port: 5173,
      proxy: {
        // 将 /api（REST + SSE 事件流）转发到后端，避免跨域。
        // 项目只用 SSE，无 WebSocket 代码，不再保留 /ws 死代理。
        '/api': {
          target: backendUrl,
          changeOrigin: true,
        },
      },
    },
    build: {
      // 拆包：框架单独成 chunk，避免首屏加载一个巨大的 bundle。
      // Vite 8（rolldown）只支持函数形式的 manualChunks。
      rollupOptions: {
        output: {
          manualChunks(id: string) {
            if (/node_modules\/(vue|vue-router|pinia|@vue)\//.test(id)) return 'vendor-vue'
            return undefined
          },
        },
      },
      chunkSizeWarningLimit: 800,
    },
  }
})
