import { beforeEach, describe, expect, it } from 'vitest'
import { useAuthStore } from '@/store/auth'
import type { UserInfo } from '@/types'

const stu: UserInfo = { id: 'u1', uid: '202300001', name: '张三', role: 'Student' }

beforeEach(() => {
  localStorage.clear()
  useAuthStore.setState({ token: null, user: null })
})

describe('auth store（登录态与权限上下文）', () => {
  it('setAuth 写入 token + user，并同步 localStorage 供 axios/fetch 拦截器读取', () => {
    useAuthStore.getState().setAuth('tok-1', stu)

    const s = useAuthStore.getState()
    expect(s.token).toBe('tok-1')
    expect(s.user?.uid).toBe('202300001')
    expect(s.user?.role).toBe('Student')
    expect(localStorage.getItem('gs_token')).toBe('tok-1')
  })

  it('logout 清空内存登录态与 gs_token', () => {
    useAuthStore.getState().setAuth('tok-1', stu)
    useAuthStore.getState().logout()

    const s = useAuthStore.getState()
    expect(s.token).toBeNull()
    expect(s.user).toBeNull()
    expect(localStorage.getItem('gs_token')).toBeNull()
  })

  it('zustand persist 落库 gs_auth，页面刷新后可恢复登录态（路由守卫依赖）', () => {
    useAuthStore.getState().setAuth('tok-2', stu)

    const raw = JSON.parse(localStorage.getItem('gs_auth') ?? '{}')
    expect(raw.state?.token).toBe('tok-2')
    expect(raw.state?.user?.role).toBe('Student')

    // 模拟重载后的 rehydrate：从持久层恢复
    useAuthStore.setState({ token: raw.state.token, user: raw.state.user })
    expect(useAuthStore.getState().token).toBe('tok-2')
  })
})
