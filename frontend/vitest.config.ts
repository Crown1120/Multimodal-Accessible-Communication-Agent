import { fileURLToPath, URL } from 'node:url'
import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vitest/config'

// 单元测试配置单独一份：
// 项目的 vite.config.ts 使用 Vite 8（rolldown），而 vitest 自带一份 Vite，
// 两者的 Plugin 类型不兼容，混在一个配置里会让 vue-tsc 报类型错误。
// 这里用 `as never` 绕过该类型冲突（运行时两者兼容），以便支持 .vue 组件测试。
export default defineConfig({
  plugins: [vue() as never],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  test: {
    environment: 'jsdom',
    include: ['src/**/*.spec.ts'],
    globals: true,
    restoreMocks: true,
  },
})
