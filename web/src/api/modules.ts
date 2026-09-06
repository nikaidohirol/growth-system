import { unwrap, http } from './http'
import type {
  ApiResponse, AuditSummaryItem, BackItem, ChatMessageItem, ChatSessionItem,
  CompForecast, DeanDashboardData, EntityMeta, EntityRecord, GpaRow, ImportResult,
  LoginResult, MetaAll, NotificationItem, ObjectionItem, OperationLog, PageData,
  Pandect, PublicityRow, RecordLog, UserInfo,
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
  /** Excel 批量导入：rows 为字段名键值对数组（kv 用 _kv_chiefly/_kv_minor，辅导员补录行内带 sid） */
  importEntities: (key: string, payload: { rows: Record<string, string>[]; status?: string }) =>
    unwrap<ImportResult>(http.post(`/entities/${key}/import`, payload)),
}

export const auditAPI = {
  summary: () =>
    unwrap<{ list: AuditSummaryItem[]; pendingTotal: number; approvedTotal: number; deanPendingTotal: number }>(
      http.get('/audit/summary')),
  records: (params: { key: string; status?: string; page?: number; pageSize?: number; keyword?: string }) =>
    unwrap<PageData<EntityRecord & { student: { uid: string; name: string; classId?: string; college?: string } }>>(
      http.get('/audit/records', { params })),
  submit: (key: string, id: string, status: '通过' | '驳回', opinion: string) =>
    unwrap<EntityRecord>(http.post(`/audit/submit/${key}/${id}`, { status, opinion })),
  /** 院长批量确认：待院长审批 → 公示期（逐条核定学分/留痕/通知） */
  batchConfirm: (key: string, ids: string[]) =>
    unwrap<{ confirmed: number; skipped: number }>(http.post(`/audit/batch/${key}`, { ids })),
}

export const objectionAPI = {
  /** 公示栏：全院「公示中」记录聚合（登录即可见） */
  publicity: () =>
    unwrap<{ list: PublicityRow[]; total: number }>(http.get('/objections/publicity')),
  /** 实名异议：{ key, recordId, reason } */
  submit: (payload: { key: string; recordId: string; reason: string }) =>
    unwrap<{ id: string }>(http.post('/objections', payload)),
  mine: () => unwrap<{ list: ObjectionItem[] }>(http.get('/objections/mine')),
  list: (params?: Record<string, unknown>) =>
    unwrap<PageData<ObjectionItem>>(http.get('/objections', { params })),
  /** 院长复核：result 成立（记录驳回）/ 不成立（维持认定） */
  review: (id: string, result: '成立' | '不成立', opinion: string) =>
    unwrap(http.post(`/objections/${id}/review`, { result, opinion })),
}

export const oplogAPI = {
  logs: (params: Record<string, unknown>) =>
    unwrap<PageData<OperationLog>>(http.get('/logs', { params })),
  recordLogs: (key: string, recordId: string) =>
    unwrap<RecordLog[]>(http.get(`/logs/record/${key}/${recordId}`)),
}

export const notificationAPI = {
  list: (params?: Record<string, unknown>) =>
    unwrap<PageData<NotificationItem> & { unread: number }>(
      http.get('/notifications', { params })),
  unread: () => unwrap<{ unread: number }>(http.get('/notifications/unread')),
  read: (payload: { ids?: string[]; all?: boolean }) =>
    unwrap(http.post('/notifications/read', payload)),
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
    unwrap<ImportResult>(http.post('/users/students', payload)),
  updateStudent: (sid: string, payload: Record<string, unknown>) =>
    unwrap(http.put(`/users/students/${sid}`, payload)),
  removeStudent: (sid: string) => unwrap(http.delete(`/users/students/${sid}`)),
  gpaList: (sid: string) => unwrap<GpaRow[]>(http.get('/gpa/list', { params: { sid } })),
  addGpa: (payload: Record<string, unknown>) => unwrap(http.post('/gpa', payload)),
  importGpa: (payload: { rows: Record<string, string>[] }) =>
    unwrap<ImportResult>(http.post('/gpa/import', payload)),
  removeGpa: (id: string) => unwrap(http.delete(`/gpa/${id}`)),
}

export const gpaAPI = {
  my: () => unwrap<GpaRow[]>(http.get('/gpa/my')),
}

export const compAPI = {
  /** 本人综测过程分测算（学生）：分项明细逐条可追溯 */
  me: () => unwrap<CompForecast | null>(http.get('/dashboard/student/comp-forecast')),
  /** 综测测算专业排名表（辅导员/院长）：同年级同专业口径，与教务导入综测并列展示 */
  list: (filters?: { major?: string; periods?: string }) =>
    unwrap<{ list: CompForecast[] }>(
      http.get('/dashboard/comp-forecast', { params: { ...filters } })),
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
  asrStatus: () => unwrap<{ available: boolean }>(http.get('/ai/asr/status')),
  asr: (blob: Blob) => {
    const fd = new FormData()
    fd.append('audio', blob, 'audio.pcm')
    // 录音按 40ms/帧 节奏上传 + 识别等待，放宽默认 30s 超时
    return unwrap<{ text: string }>(
      http.post('/ai/asr', fd, {
        headers: { 'Content-Type': 'multipart/form-data' },
        timeout: 90000,
      }))
  },
}

export type { ApiResponse }
