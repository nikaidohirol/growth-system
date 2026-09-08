import { expect, type Page, test } from '@playwright/test'

/**
 * E2E 冒烟：系统主干三链路（最小版）
 *   登录 → 学生申报社会实践 → 辅导员审核通过 → 状态进入公示中 → 学生侧可见
 * 断言只锁「业务状态机是否咬合」，表单细节/权限分支由 pytest + Vitest 分层覆盖。
 */

const TEAM = `E2E冒烟实践团-${Date.now()}`

async function login(page: Page, uid: string) {
  await page.goto('/login')
  await page.getByPlaceholder('学号 / 工号').fill(uid)
  await page.getByPlaceholder('密码').fill('123456')
  await page.getByRole('button', { name: '登 录' }).click()
  // 登录成功即重定向主面板（antd message 文本节点嵌套，用 URL 断言更稳）
  await expect(page).toHaveURL(/\/dashboard/)
}

/** antd DatePicker：填入日期后回车收起面板 */
async function pickDate(page: Page, label: string, value: string) {
  const input = page.getByLabel(label)
  await input.click()
  await input.fill(value)
  await input.press('Enter')
}

test('学生申报 → 辅导员审核通过 → 公示中', async ({ browser }) => {
  // ---- 学生：登录 + 申报社会实践 ----
  const stuCtx = await browser.newContext()
  const stu = await stuCtx.newPage()
  await login(stu, '202300001')

  await stu.goto('/entity/practice')
  await stu.getByRole('button', { name: '新增申请' }).click()
  await expect(stu.getByText('新增社会实践活动')).toBeVisible()

  await stu.getByLabel('实践团队名称').fill(TEAM)
  await stu.getByLabel('实践类型').click() // antd Select，取第一个合法选项即可
  await stu.locator('.ant-select-dropdown:not(.ant-select-dropdown-hidden) .ant-select-item-option')
    .first().click()
  await stu.getByLabel('实践主题').fill('校园垃圾分类调研')
  await stu.getByLabel('主办单位').fill('汽车工程学院团委')
  await pickDate(stu, '开始日期', '2026-09-01')
  await pickDate(stu, '结束日期', '2026-09-05')
  await stu.getByRole('button', { name: '提交申请' }).click()
  await expect(stu.getByText('提交成功，等待审核').first()).toBeVisible()

  // 学生列表即时出现该记录，状态待审核
  const stuRow = stu.locator('tr', { hasText: TEAM })
  await expect(stuRow).toBeVisible()
  await expect(stuRow.getByText('待审核')).toBeVisible()

  // ---- 辅导员：审核中心检索 + 通过 ----
  const counCtx = await browser.newContext()
  const coun = await counCtx.newPage()
  await login(coun, 'C0001')

  await coun.goto('/audit')
  // 默认停在「创新创业」组，先切到社会实践组（实体自动切为社会实践活动）
  await coun.getByText('社会实践', { exact: true }).click()
  const search = coun.getByPlaceholder('学生姓名 / 学号')
  await search.fill('202300001')
  await search.press('Enter')

  const row = coun.locator('tr', { hasText: TEAM })
  await expect(row).toBeVisible()
  await expect(row.getByText('待审核')).toBeVisible()
  // antd 按钮可访问名含图标 aria-label 前缀（如 "check 通过"），用子串匹配
  await row.getByRole('button', { name: '通过' }).click()
  // 日常类实体：辅导员直达公示期；服务端核定学分 + 留痕 + 通知学生
  await expect(coun.getByText('已通过终审，进入公示期').first()).toBeVisible()

  // ---- 学生侧确认状态流转 ----
  await stu.goto('/entity/practice')
  await expect(stu.locator('tr', { hasText: TEAM }).getByText('公示中')).toBeVisible()

  await stuCtx.close()
  await counCtx.close()
})
