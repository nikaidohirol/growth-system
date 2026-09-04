import { unwrap, http } from './http'
import type {
  ApiResponse, AuditSummaryItem, BackItem, ChatMessageItem, ChatSessionItem,
  DeanDashboardData, EntityMeta, EntityRecord, GpaRow, LoginResult,
  MetaAll, PageData, Pandect, UserInfo,
} from '@/types'

export const authAPI = {
  login: (uid: string, password: string) =>
    unwrap<LoginResult>(http.post('/auth/login', { uid, password })),
  me: () => unwrap<UserInfo>(http.get('/auth/me')),
  updateMe: (payload: Partial<UserInfo>) => unwrap<UserInfo>(http.put('/auth/me', payload)),
  changePassword: (oldPassword: string, newPassword: string) =>
    unwrap(http.put('/auth/password', { oldPassword, newPassword })),
}

export const metaAPI = {
  all: () => unwrap<MetaAll>(http.get('/meta/all')),
  entities: () => unwrap<EntityMeta[]>(http.get('/meta/entities')),
}

export const entityAPI = {
  list: (key: string, params: Record<string, unknown>) =>
    unwrap<PageData<EntityRecord>>(http.get(`/entities/${key}`, { params })),
  create: (key: string, payload: Record<string, unknown>) =>
    unwrap<EntityRecord>(http.post(`/entities/${key}`, payload)),
  update: (key: string, id: string, payload: Record<string, unknown>) =>
    unwrap<EntityRecord>(http.put(`/entities/${key}/${id}`, payload)),
  remove: (key: string, id: string) => unwrap(http.delete(`/entities/${key}/${id}`)),
  detail: (key: string, id: string) =>
    unwrap<EntityRecord>(http.get(`/entities/${key}/${id}`)),
}

export const auditAPI = {
  summary: () =>
    unwrap<{ list: AuditSummaryItem[]; pendingTotal: number; approvedTotal: number }>(
      http.get('/audit/summary')),
  records: (params: { key: string; status?: string; page?: number; pageSize?: number; keyword?: string }) =>
    unwrap<PageData<EntityRecord & { student: { uid: string; name: string; classId?: string; college?: string } }>>(
      http.get('/audit/records', { params })),
  submit: (key: string, id: string, status: '通过' | '驳回', opinion: string) =>
    unwrap(http.post(`/audit/submit/${key}/${id}`, { status, opinion })),
}

export const dashboardAPI = {
  pandect: () => unwrap<Pandect>(http.get('/dashboard/student/pandect')),
  backlist: () => unwrap<BackItem[]>(http.get('/dashboard/student/backlist')),
  counsellor: () => unwrap<{ list: AuditSummaryItem[] }>(http.get('/dashboard/counsellor')),
  dean: () => unwrap<DeanDashboardData>(http.get('/dashboard/dean')),
}

export const userAPI = {
  students: (params: Record<string, unknown>) =>
    unwrap<PageData<Record<string, any>>>(http.get('/users/students', { params })),
  addStudents: (payload: Record<string, unknown> | Record<string, unknown>[]) =>
    unwrap<{ created: string[]; skipped: string[] }>(http.post('/users/students', payload)),
  updateStudent: (sid: string, payload: Record<string, unknown>) =>
    unwrap(http.put(`/users/students/${sid}`, payload)),
  removeStudent: (sid: string) => unwrap(http.delete(`/users/students/${sid}`)),
  gpaList: (sid: string) => unwrap<GpaRow[]>(http.get('/gpa/list', { params: { sid } })),
  addGpa: (payload: Record<string, unknown>) => unwrap(http.post('/gpa', payload)),
  removeGpa: (id: string) => unwrap(http.delete(`/gpa/${id}`)),
}

export const gpaAPI = {
  my: () => unwrap<GpaRow[]>(http.get('/gpa/my')),
}

export const experienceAPI = {
  list: () => unwrap<Record<string, any>[]>(http.get('/experience')),
  add: (payload: Record<string, unknown>) => unwrap(http.post('/experience', payload)),
  update: (id: string, payload: Record<string, unknown>) =>
    unwrap(http.put(`/experience/${id}`, payload)),
  remove: (id: string) => unwrap(http.delete(`/experience/${id}`)),
}

export const exportAPI = {
  dossier: (sid?: string) =>
    unwrap<Record<string, any>>(http.get('/export/dossier', { params: sid ? { sid } : {} })),
}

export const filesAPI = {
  upload: (files: File[]) => {
    const fd = new FormData()
    files.forEach((f) => fd.append('files', f))
    return unwrap<{ label: string; url: string }[]>(
      http.post('/files/upload', fd, { headers: { 'Content-Type': 'multipart/form-data' } }))
  },
}

export const aiAPI = {
  formAssist: (entityKey: string, description: string) =>
    unwrap<{ fields: Record<string, string> }>(
      http.post('/ai/form-assist', { entityKey, description })),
  auditAssist: (entityKey: string, item: Record<string, unknown>) =>
    unwrap<{ suggestion: string; reason: string }>(
      http.post('/ai/audit-assist', { entityKey, item })),
  sessions: () => unwrap<ChatSessionItem[]>(http.get('/ai/sessions')),
  sessionMessages: (sid: string) => unwrap<ChatMessageItem[]>(http.get(`/ai/sessions/${sid}/messages`)),
  removeSession: (sid: string) => unwrap(http.delete(`/ai/sessions/${sid}`)),
  tts: async (text: string): Promise<ArrayBuffer | null> => {
    try {
      const r = await http.post('/ai/tts', { text }, { responseType: 'arraybuffer' })
      return r.data as ArrayBuffer
    } catch {
      return null // 501 → 前端降级浏览器合成
    }
  },
}

export type { ApiResponse }
