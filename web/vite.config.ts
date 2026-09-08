/// <reference types="vitest/config" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'node:path'

// 端口规范：前端 3000，代理到后端 8000
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { '@': path.resolve(__dirname, 'src') },
  },
  server: {
    port: 3000,
    proxy: {
      '/api': { target: 'http://localhost:8000', changeOrigin: true },
      '/files': { target: 'http://localhost:8000', changeOrigin: true },
    },
  },
  // E2E 冒烟：preview 起独立后端（端口 8100），经 VITE_API_TARGET 注入，避开本地 dev 的 8000
  preview: {
    port: 4173,
    proxy: {
      '/api': { target: process.env.VITE_API_TARGET ?? 'http://localhost:8000', changeOrigin: true },
      '/files': { target: process.env.VITE_API_TARGET ?? 'http://localhost:8000', changeOrigin: true },
    },
  },
  // Vitest 单测：jsdom + RTL，与 vite 共用插件/别名；e2e/ 归 Playwright，不纳入单测
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: './src/test/setup.ts',
    css: false,
    exclude: ['**/node_modules/**', '**/dist/**', 'e2e/**'],
  },
})
