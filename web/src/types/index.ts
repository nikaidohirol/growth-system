// 全局类型定义 — 与后端契约一一对应
export interface ApiResponse<T = unknown> {
  code: number
  message: string
  data: T
}

export interface PageData<T = Record<string, unknown>> {
  list: T[]
  total: number
  page: number
  pageSize: number
}

export type Role = 'Student' | 'Counsellor' | 'Dean'

export interface UserInfo {
  id: string
  uid: string
  name: string
  role: Role
  sex?: string
  politicsStatus?: string
  phone?: string
  email?: string
  classId?: string
  periods?: string
  college?: string
  major?: string
  photo?: string
  title?: string
  counsellorName?: string
}

export interface LoginResult {
  token: string
  user: UserInfo
}

// ---- 实体注册表契约（/api/meta/entities）----
export interface FieldMeta {
  name: string
  label: string
  type: 'text' | 'textarea' | 'number' | 'date' | 'select' | 'cascader' | 'kv'
  required: boolean
  options?: string          // 字典 key
  kvCategory?: string       // type=kv 时的创新类别
  placeholder?: string
  inTable: boolean
  half: boolean
}

export interface EntityMeta {
  key: string
  label: string
  group: 'practice' | 'inn' | 'other'
  searchPlaceholder: string
  searchFields: string[]
  fields: FieldMeta[]
}

export interface EntityRecord {
  id: string
  status: '待审核' | '通过' | '驳回'
  auditor?: string
  opinion?: string
  auditTime?: string
  files: { label: string; url: string }[]
  createdAt: string
  [key: string]: unknown
}

// ---- 字典（/api/meta/all）----
export interface InnovateKVItem {
  label: string
  chiefly_label: string
  minor_label: string
  kv: Record<string, Record<string, number>>
}

export interface CreditRules {
  min_inn: number
  min_pra: number
  min_sum: number
  practice_credit: number
  practice_cap: number
  voluntary_hours_per_credit: number
  voluntary_credit: number
  voluntary_cap: number
}

export interface MetaAll {
  college_major: Record<string, string[]>
  periods: string[]
  politics_status: string[]
  honor_level: string[]
  practice_type: string[]
  party_type: string[]
  organ_cascader: Record<string, string[]>
  credit_rules: CreditRules
  innovate_kv: Record<string, InnovateKVItem>
}

// ---- 看板 ----
export interface Pandect {
  innCredit: number
  praCredit: number
  sumCredit: number
  innCreditList: { key: string; value: number }[]
  practiceCreditList: { key: string; value: number }[]
  rules: CreditRules
  practiceCount: number
  voluntaryHours: number
}

export interface BackItem {
  key: string
  label: string
  title: string
  opinion?: string
  auditTime?: string
  id: string
}

export interface AuditSummaryItem {
  key: string
  label: string
  group: string
  count: number
}

export interface DeanDashboardData {
  totalStudents: number
  totalCounsellors: number
  pendingTotal: number
  approvedTotal: number
  innByCategory: { key: string; value: number }[]
  studentsByCollege: { key: string; value: number }[]
  avgGpaTrend: { key: string; value: number }[]
}

export interface GpaRow {
  id: string
  semester: string
  college?: string
  major?: string
  mutual: number
  comp: number
  gpa: number
  gpaRank: number
  compRank: number
  maxRank: number
}

export interface ChatMessageItem {
  id: string
  role: 'user' | 'assistant'
  content: string
  sources: { content: string; source: string; title: string }[]
}

export interface ChatSessionItem {
  id: string
  title: string
  createdAt: string
}
