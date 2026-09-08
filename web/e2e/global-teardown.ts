import { rmSync } from 'node:fs'
import { E2E_DB, killChildren } from './global-setup'

/** 回收子进程与临时库文件 */
export default async function globalTeardown() {
  await killChildren()
  for (const f of [E2E_DB, `${E2E_DB}-journal`]) {
    try { rmSync(f, { force: true }) } catch { /* 临时目录残留无害，交给系统清理 */ }
  }
}
