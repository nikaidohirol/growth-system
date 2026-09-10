import { defineConfig } from '@playwright/test'

/**
 * E2E 冒烟测试（最小版）：
 *   - 1 个 spec，3 条核心链路：登录 → 学生申报 → 辅导员审核 → 公示中
 *   - 仅 chromium，不做多浏览器矩阵
 *   - 后端（8100）与前端 preview（4173）由 global-setup 拉起，避免与本地 dev 8000 冲突
 * 本地运行：npm run e2e（先构建 dist 再跑浏览器）；CI 独立 job
 */
export default defineConfig({
  testDir: './e2e',
  timeout: 150_000, // 全链路含两次登录/种子库预热后的多次导航，60s 不够
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [['list'], ['html', { open: 'never' }]] : 'list',
  globalSetup: './e2e/global-setup.ts',
  globalTeardown: './e2e/global-teardown.ts',
  use: {
    baseURL: 'http://127.0.0.1:4173', // 与 global-setup 的 preview 绑定一致，避免 localhost 解析歧义
    trace: 'retain-on-failure',
    locale: 'zh-CN',
  },
})
