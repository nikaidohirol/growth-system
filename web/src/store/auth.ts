import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { UserInfo } from '@/types'

interface AuthState {
  token: string | null
  user: UserInfo | null
  setAuth: (token: string, user: UserInfo) => void
  setUser: (user: UserInfo) => void
  logout: () => void
}

// token 同时落 localStorage 一份供 axios/fetch 拦截器同步读取
export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      token: null,
      user: null,
      setAuth: (token, user) => {
        localStorage.setItem('gs_token', token)
        set({ token, user })
      },
      setUser: (user) => set({ user }),
      logout: () => {
        localStorage.removeItem('gs_token')
        set({ token: null, user: null })
      },
    }),
    { name: 'gs_auth' },
  ),
)
