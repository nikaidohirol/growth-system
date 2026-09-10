import axios from 'axios'
import { message } from 'antd'
import type { ApiResponse } from '@/types'

export const http = axios.create({
  baseURL: import.meta.env.VITE_API_BASE || '/api',
  timeout: 30000,
})

// 请求注入 Bearer Token；401 统一清除登录态
http.interceptors.request.use((config) => {
  const token = localStorage.getItem('gs_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

http.interceptors.response.use(
  (resp) => {
    const body = resp.data as ApiResponse
    if (body && typeof body === 'object' && 'code' in body && body.code !== 0) {
      message.error(body.message || '请求失败')
      return Promise.reject(new Error(body.message))
    }
    return resp
  },
  (error) => {
    const status = error.response?.status
    const detail = error.response?.data?.detail
    if (status === 401) {
      localStorage.removeItem('gs_token')
      localStorage.removeItem('gs_user')
      // 登录页自身的 401 = 账号或密码错误，由登录页内联 Alert 常驻展示；其余页面的 401 = 登录过期
      if (!location.pathname.startsWith('/login')) {
        message.warning('登录已过期，请重新登录')
        location.href = '/login'
      }
    } else if (detail) {
      message.error(typeof detail === 'string' ? detail : '请求失败')
    } else {
      message.error(error.message || '网络异常')
    }
    return Promise.reject(error)
  },
)

/** 解包 {code,data} → data */
export async function unwrap<T>(p: Promise<{ data: ApiResponse<T> }>): Promise<T> {
  const r = await p
  return r.data.data
}

// ---- SSE 流式请求（fetch 读取，支持 POST 与中断）----
export interface SSECallbacks {
  onEvent: (event: string, data: any) => void
  signal?: AbortSignal
}

export async function ssePost(url: string, body: unknown, cb: SSECallbacks) {
  const token = localStorage.getItem('gs_token')
  const resp = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
    body: JSON.stringify(body),
    signal: cb.signal,
  })
  if (!resp.ok || !resp.body) throw new Error(`SSE 请求失败：${resp.status}`)
  const reader = resp.body.getReader()
  const decoder = new TextDecoder()
  let buf = ''
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    buf += decoder.decode(value, { stream: true })
    let idx
    while ((idx = buf.indexOf('\n\n')) >= 0) {
      const raw = buf.slice(0, idx)
      buf = buf.slice(idx + 2)
      let event = 'message'
      const dataLines: string[] = []
      for (const line of raw.split('\n')) {
        if (line.startsWith('event:')) event = line.slice(6).trim()
        else if (line.startsWith('data:')) dataLines.push(line.slice(5).trim())
      }
      if (dataLines.length) {
        try {
          cb.onEvent(event, JSON.parse(dataLines.join('\n')))
        } catch {
          /* 忽略不完整帧 */
        }
      }
    }
  }
}
