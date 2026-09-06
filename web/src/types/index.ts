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
  deanReview: boolean       // true=辅导员仅初审，院长终审
  searchPlaceholder: string
  searchFields: string[]
  fields: FieldMeta[]
}

/** 审核流状态：待审核 →(辅导员通过·院长终审类)→ 待院长审批 →(院长通过)→ 公示中 →(期满)→ 通过 */
export type AuditStatus = '待审核' | '待院长审批' | '公示中' | '通过' | '驳回'

export interface EntityRecord {
  id: string
  status: AuditStatus
  auditor?: string
  opinion?: string
  auditTime?: string
  publicEnd?: string | null // 公示截止时间（公示中状态使用）
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
  /** 人员次序折算系数（竞赛类启用）：次序 → 系数 */
  post_factor?: Record<string, number>
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
  /** 审核流配置：公示期天数 + 本学期学生申报窗口（窗口外仅辅导员/院长补录） */
  audit_flow: { publicityDays: number; windowStart: string; windowEnd: string }
  /** 综测测算规则矩阵（服务端唯一事实源，仅作展示口径说明用） */
  comp_rule?: {
    weights: { academic: number; moral: number; sports: number }
    innovation: { cap: number }
  }
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

/** 院长看板：各辅导员初审通过率（宏观监督） */
export interface CounsellorStat {
  name: string
  total: number
  passed: number
  rate: number
}

/** 操作日志（合规留痕，只增不删） */
export interface OperationLog {
  id: string
  uid: string
  operatorName: string
  role: Role
  action: 'create' | 'update' | 'delete' | 'audit' | 'login'
  entityKey?: string | null
  entityLabel?: string | null
  recordId?: string | null
  sid?: string | null
  summary: string
  createdAt: string
}

/** 单条记录的操作时间线条目 */
export interface RecordLog {
  action: OperationLog['action']
  operatorName: string
  role: Role
  summary: string
  createdAt: string
}

/** 站内通知（消息触达：审核结论/系统提醒） */
export interface NotificationItem {
  id: string
  title: string
  content: string
  type: 'audit' | 'system' | string
  linkKey?: string | null
  linkId?: string | null
  isRead: boolean
  createdAt: string
}

// ---- 公示异议（公示期监督闭环） ----
export interface PublicityRow {
  key: string
  recordId: string
  label: string
  title: string
  credit: number | null
  sid: string
  publicEnd: string
  student: { name: string; classId: string | null }
}

export interface ObjectionItem {
  id: string
  key: string
  recordId: string
  label: string
  title: string
  reason: string
  status: '待复核' | '成立' | '不成立'
  objector: { uid: string; name: string }
  handledBy: string | null
  handledTime: string | null
  createdAt: string
  owner?: { name: string; classId: string | null }
}

export interface DeanDashboardData {
  totalStudents: number
  totalCounsellors: number
  pendingTotal: number
  approvedTotal: number
  deanPendingTotal: number
  publicTotal: number
  counsellorStats: CounsellorStat[]
  innByCategory: { key: string; value: number }[]
  studentsByGrade: { key: string; value: number }[]
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

// ---- 综测过程分测算（读时计算，只统计已生效记录；服务端唯一事实源） ----
/** 加分明细：key=实体 key（可追溯跳转），recordId=来源记录 */
export interface CompBonusItem {
  key: string
  recordId: string
  label: string
  score: number
}

export interface CompForecast {
  sid: string
  uid: string
  name: string
  classId: string | null
  major: string | null
  periods: string | null
  /** 学业：最近学期 GPA×换算系数 */
  academic: { gpa: number | null; score: number; semester: string | null }
  /** 教务导入的权威综测（与系统测算并存对照） */
  imported: { comp: number; compRank: number; maxRank: number } | null
  moral: { base: number; score: number; items: CompBonusItem[] }
  sports: { base: number; score: number; items: CompBonusItem[] }
  innovation: { bonus: number; items: CompBonusItem[]; capped: boolean }
  total: number
  /** 专业内排名（同年级同专业口径，评奖/保研口径） */
  majorRank: number
  majorSize: number
}

// ---- Excel 批量导入 ----
export interface ImportRowError {
  row: number
  message: string
}

export interface ImportResult {
  created: number
  skipped?: string[]
  errors: ImportRowError[]
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
