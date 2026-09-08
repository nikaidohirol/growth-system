import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App from '@/App'
import { useAuthStore } from '@/store/auth'
import { useMetaStore } from '@/store/meta'
import type { UserInfo } from '@/types'

/**
 * 路由级权限矩阵（RBAC 前端半边）：
 *   未登录 → /login；越权访问 → /dashboard；角色匹配 → 页面渲染
 *   MainLayout 菜单按角色过滤（Student 业务页 / Counsellor 审核页 / Dean 复核页）
 * 页面内部逻辑在各自测试文件覆盖，这里桩化隔离，只测权限层。
 */

vi.mock('@/pages/Login', () => ({ default: () => <div>LoginPage</div> }))
vi.mock('@/pages/dashboard/Dashboard', () => ({ default: () => <div>DashboardPage</div> }))
vi.mock('@/pages/student/EntityPage', () => ({ default: () => <div>EntityPageStub</div> }))
vi.mock('@/pages/student/GradePage', () => ({ default: () => <div>GradePageStub</div> }))
vi.mock('@/pages/counsellor/AuditCenter', () => ({ default: () => <div>AuditCenterPage</div> }))
vi.mock('@/pages/counsellor/StudentManage', () => ({ default: () => <div>StudentManagePage</div> }))
vi.mock('@/components/chat/AIChatDrawer', () => ({ default: () => null }))
vi.mock('@/components/layout/NotificationDrawer', () => ({ default: () => null }))
vi.mock('@/api/modules', () => ({
  metaAPI: { all: vi.fn(), entities: vi.fn() },
  notificationAPI: { unread: vi.fn(async () => ({ code: 0, data: { unread: 0 } })) },
}))

const users: Record<string, UserInfo> = {
  student: { id: 'u1', uid: '202300001', name: '张三', role: 'Student' },
  counsellor: { id: 'u2', uid: 'C0001', name: '李文静', role: 'Counsellor' },
  dean: { id: 'u3', uid: 'D0001', name: '王建国', role: 'Dean' },
}

function loginAs(role: keyof typeof users | null) {
  useAuthStore.setState(role ? { token: 'tok', user: users[role] } : { token: null, user: null })
}

function renderApp(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>,
  )
}

beforeEach(() => {
  useMetaStore.setState({ loaded: true, meta: null, entities: [] }) // 跳过 Bootstrap 字典预取
})

describe('路由守卫 Guard', () => {
  it('未登录访问受保护路由 → 重定向登录页', async () => {
    loginAs(null)
    renderApp('/audit')

    expect(await screen.findByText('LoginPage')).toBeInTheDocument()
    expect(screen.queryByText('AuditCenterPage')).not.toBeInTheDocument()
  })

  it('学生访问审核中心（Counsellor/Dean 专属）→ 重定向主面板', async () => {
    loginAs('student')
    renderApp('/audit')

    expect(await screen.findByText('DashboardPage')).toBeInTheDocument()
    expect(screen.queryByText('AuditCenterPage')).not.toBeInTheDocument()
  })

  it('辅导员访问学生专属页（综合素质成绩）→ 重定向主面板', async () => {
    loginAs('counsellor')
    renderApp('/grade')

    expect(await screen.findByText('DashboardPage')).toBeInTheDocument()
    expect(screen.queryByText('GradePageStub')).not.toBeInTheDocument()
  })

  it('辅导员访问审核中心 → 正常渲染', async () => {
    loginAs('counsellor')
    renderApp('/audit')

    expect(await screen.findByText('AuditCenterPage')).toBeInTheDocument()
  })

  it('院长访问学生管理 → 正常渲染（Counsellor/Dean 共享审核侧路由）', async () => {
    loginAs('dean')
    renderApp('/students')

    expect(await screen.findByText('StudentManagePage')).toBeInTheDocument()
  })
})

describe('侧边菜单按角色过滤', () => {
  it('学生：业务申报菜单，无审核中心/学生管理', async () => {
    loginAs('student')
    renderApp('/dashboard')

    expect(await screen.findByText('综合素质成绩')).toBeInTheDocument()
    expect(screen.getByText('成长档案')).toBeInTheDocument()
    expect(screen.getByText('个人荣誉')).toBeInTheDocument()
    expect(screen.queryByText('审核中心')).not.toBeInTheDocument()
    expect(screen.queryByText('学生管理')).not.toBeInTheDocument()
  })

  it('辅导员：审核侧菜单，无学生申报菜单', async () => {
    loginAs('counsellor')
    renderApp('/dashboard')

    expect(await screen.findByText('审核中心')).toBeInTheDocument()
    expect(screen.getByText('学生管理')).toBeInTheDocument()
    expect(screen.getByText('操作日志')).toBeInTheDocument()
    expect(screen.queryByText('成长档案')).not.toBeInTheDocument()
    expect(screen.queryByText('综合素质成绩')).not.toBeInTheDocument()
  })

  it('院长：复核菜单（公示异议复核），无学生管理入口', async () => {
    loginAs('dean')
    renderApp('/dashboard')

    expect(await screen.findByText('公示异议复核')).toBeInTheDocument()
    expect(screen.getByText('审核中心')).toBeInTheDocument()
    expect(screen.queryByText('学生管理')).not.toBeInTheDocument()
    expect(screen.queryByText('成长档案')).not.toBeInTheDocument()
  })
})
