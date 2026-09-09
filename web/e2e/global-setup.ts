import { spawn } from 'node:child_process'
import { existsSync, rmSync } from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import process from 'node:process'
import { fileURLToPath } from 'node:url'

/**
 * E2E 全局准备：拉起独立后端（8100，一次性 SQLite 种子库）+ 前端 preview（4173）。
 * 全部走 playwright 子进程编排，测试结束由 global-teardown 统一回收。
 */

const HERE = path.dirname(fileURLToPath(import.meta.url)) // web/e2e
const ROOT = path.resolve(HERE, '../..')                  // growth-system
export const E2E_DB = path.join(os.tmpdir(), `growth-e2e-${process.pid}.db`)
export const BACKEND_PORT = 8100
export const FRONTEND_PORT = 4173

let backend: ReturnType<typeof spawn> | undefined
let frontend: ReturnType<typeof spawn> | undefined

/** 回收子进程（teardown 调用）；Windows 须等进程真正退出，否则 SQLite 文件句柄未释放 */
export async function killChildren() {
  const exitWithin = (child: ReturnType<typeof spawn> | undefined, ms: number) =>
    new Promise<void>(res => {
      if (!child || child.exitCode !== null || child.signalCode) return res()
      const t = setTimeout(res, ms)
      child.once('exit', () => { clearTimeout(t); res() })
      child.kill()
    })
  await exitWithin(frontend, 5000)
  await exitWithin(backend, 5000)
}

async function waitHealthy(url: string, label: string, tries = 240): Promise<void> {
  for (let i = 0; i < tries; i++) {
    try {
      const r = await fetch(url)
      if (r.ok) return
    }
    catch { /* 服务未就绪，继续等 */ }
    await new Promise(r => setTimeout(r, 1000))
  }
  throw new Error(`E2E: ${label} 未在 ${tries}s 内就绪（${url}）`)
}

export default async function globalSetup() {
  // 一次性种子库：每次 E2E 从空库重建，断言与历史数据解耦
  for (const f of [E2E_DB, `${E2E_DB}-journal`]) rmSync(f, { force: true })

  // 后端解释器：本地用 server/.venv，CI 用系统 python3/python
  const candidates = process.platform === 'win32'
    ? [path.join(ROOT, 'server/.venv/Scripts/python.exe'), 'python']
    : [path.join(ROOT, 'server/.venv/bin/python'), 'python3', 'python']
  const python = candidates.find(c => c.includes('.venv') ? existsSync(c) : true)!

  const serverEnv = {
    ...process.env,
    DATABASE_URL: `sqlite+aiosqlite:///${E2E_DB}`,
    SEED_RESET: '1',                // seed.py 先 drop 重建，保证空库起点
    GROWTH_WINDOW_ALWAYS_OPEN: '1', // 申报窗口与运行日期解耦（meta.py 测试钩子）
    LLM_API_KEY: '',
  }

  // 灌一次性种子库（Docker 里由 entrypoint 做，此处直接跑 seed.py）
  await new Promise<void>((resolve, reject) => {
    const seed = spawn(python, ['seed.py'], {
      cwd: path.join(ROOT, 'server'), env: serverEnv, stdio: 'inherit',
    })
    seed.on('exit', code => code === 0
      ? resolve()
      : reject(new Error(`E2E: seed.py 退出码 ${code}`)))
    seed.on('error', reject)
  })

  backend = spawn(python, ['-m', 'uvicorn', 'main:app', '--host', '127.0.0.1',
    '--port', String(BACKEND_PORT)], {
    cwd: path.join(ROOT, 'server'),
    env: serverEnv,
    stdio: 'inherit',
  })
  await waitHealthy(`http://127.0.0.1:${BACKEND_PORT}/api/health`, '后端')

  // 前端 preview（dist 须已构建，npm run e2e 先跑 build），代理指向独立后端
  frontend = spawn(process.execPath,
    ['node_modules/vite/bin/vite.js', 'preview', '--port', String(FRONTEND_PORT), '--strictPort'], {
      cwd: path.resolve(HERE, '..'),
      env: { ...process.env, VITE_API_TARGET: `http://127.0.0.1:${BACKEND_PORT}` },
      stdio: 'inherit',
    })
  await waitHealthy(`http://127.0.0.1:${FRONTEND_PORT}`, '前端 preview')
}
