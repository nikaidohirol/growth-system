import { Cascader, DatePicker, Input, InputNumber, Select, Space, Typography } from 'antd'
import type { FormInstance } from 'antd'
import dayjs from 'dayjs'
import type { FieldMeta, MetaAll } from '@/types'

const { Text } = Typography

/** 规则矩阵核定预览：基准分 × 人员次序系数（与后端 assess_inn_credit 同口径） */
export function computeCredit(
  meta: MetaAll,
  kvCategory: string | undefined,
  kvValue?: string | null,
  post?: string | null,
): { base: number; factor: number; credit: number } | null {
  const conf = kvCategory ? meta.innovate_kv[kvCategory] : undefined
  if (!conf || !kvValue) return null
  const [chiefly, minor] = String(kvValue).split(/[·/]/).map((s) => s.trim())
  const base = conf.kv[chiefly]?.[minor]
  if (base === undefined) return null
  let factor = 1
  if (conf.post_factor && post) factor = conf.post_factor[post] ?? 1
  return { base, factor, credit: Math.round(base * factor * 100) / 100 }
}

/** 学分认定二级联动（kv 类型）：chiefly → minor → 实时核定预览 */
function KvField({ field, meta, value, onChange, post }: {
  field: FieldMeta
  meta: MetaAll
  value?: { chiefly?: string; minor?: string }
  onChange: (v: { chiefly?: string; minor?: string }) => void
  post?: string
}) {
  const conf = meta.innovate_kv[field.kvCategory ?? '']
  if (!conf) return null
  const chiefies = Object.keys(conf.kv)
  const minors = value?.chiefly ? Object.keys(conf.kv[value.chiefly] ?? {}) : []
  const base = value?.chiefly && value?.minor ? conf.kv[value.chiefly]?.[value.minor] : undefined
  const factor = conf.post_factor && post ? (conf.post_factor[post] ?? 1) : 1
  return (
    <Space direction="vertical" style={{ width: '100%' }} size={4}>
      <Space wrap>
        <Select
          style={{ width: 180 }}
          placeholder={conf.chiefly_label}
          value={value?.chiefly}
          options={chiefies.map((k) => ({ value: k, label: k }))}
          onChange={(chiefly) => onChange({ chiefly, minor: undefined })}
        />
        <Select
          style={{ width: 160 }}
          placeholder={conf.minor_label}
          value={value?.minor}
          disabled={!value?.chiefly}
          options={minors.map((k) => ({ value: k, label: k }))}
          onChange={(minor) => onChange({ ...value, minor })}
        />
      </Space>
      <Text type={base === undefined ? 'secondary' : 'warning'} style={{ fontSize: 12 }}>
        {base === undefined
          ? `选择${conf.chiefly_label}与${conf.minor_label}后按规则矩阵自动核定学分`
          : factor !== 1
            ? `核定学分：${base} × ${factor}（${post}）= ${Math.round(base * factor * 100) / 100} 学分`
            : `核定学分：${base} 学分（按认定规则自动核定）`}
      </Text>
    </Space>
  )
}

/** 表单字段渲染器 — 由实体契约驱动（form 实例由调用方传入） */
export function renderFormField(
  field: FieldMeta,
  meta: MetaAll,
  form: FormInstance,
  kvValue?: { chiefly?: string; minor?: string },
  onKvChange?: (v: { chiefly?: string; minor?: string }) => void,
  postValue?: string,
) {
  const common = { placeholder: field.placeholder || `请输入${field.label}`, style: { width: '100%' } }
  switch (field.type) {
    case 'textarea':
      return <Input.TextArea rows={3} {...common} />
    case 'number':
      return <InputNumber min={0} style={{ width: '100%' }} placeholder={`请输入${field.label}`} />
    case 'date':
      return <DatePicker style={{ width: '100%' }} />
    case 'select': {
      const options = (meta as any)[field.options ?? ''] as string[] | undefined
      return (
        <Select
          allowClear
          placeholder={`请选择${field.label}`}
          options={(options ?? []).map((o) => ({ value: o, label: o }))}
        />
      )
    }
    case 'cascader': {
      const tree = (meta as any)[field.options ?? ''] as Record<string, string[]> | undefined
      return (
        <Cascader
          placeholder={`请选择${field.label}`}
          options={Object.entries(tree ?? {}).map(([t, posts]) => ({
            value: t,
            label: t,
            children: posts.map((p) => ({ value: p, label: p })),
          }))}
          onChange={(_, selected) => {
            // 组织经历：级联同时回填 type 与 post
            form.setFieldValue('post', selected?.[1] ?? undefined)
          }}
        />
      )
    }
    case 'kv':
      return <KvField field={field} meta={meta} value={kvValue} post={postValue}
                      onChange={(v) => onKvChange?.(v)} />
    default:
      return <Input {...common} />
  }
}

/** 表单值 → 请求 payload（date 序列化、kv 拆字段、cascader 拆字段） */
export function formToPayload(
  e: { fields: FieldMeta[] },
  values: Record<string, any>,
  kvState: { chiefly?: string; minor?: string },
): Record<string, unknown> {
  const payload: Record<string, unknown> = {}
  for (const f of e.fields) {
    const v = values[f.name]
    if (v === undefined || v === null) continue
    if (f.type === 'date') payload[f.name] = dayjs.isDayjs(v) ? v.format('YYYY-MM-DD') : String(v)
    else if (f.type !== 'kv') payload[f.name] = v
  }
  if (kvState.chiefly && kvState.minor) {
    payload._kv_chiefly = kvState.chiefly
    payload._kv_minor = kvState.minor
  }
  payload.files = values.files ?? []
  return payload
}

/** 记录行 → 表单初始值（kv 从 "A·B" 拆回两级，兼容旧数据 "A / B" 分隔） */
export function recordToForm(
  e: { fields: FieldMeta[] },
  record: Record<string, any>,
): Record<string, any> {
  const form: Record<string, any> = { ...record }
  for (const f of e.fields) {
    if (f.type === 'date' && record[f.name]) form[f.name] = dayjs(record[f.name])
    if (f.type === 'kv' && record[f.name]) {
      const [chiefly, minor] = String(record[f.name]).split(/[·/]/).map((s) => s.trim())
      form._kv = { chiefly, minor }
    }
    if (f.type === 'cascader' && record[f.name]) form[f.name] = [record[f.name], record.post]
  }
  return form
}
