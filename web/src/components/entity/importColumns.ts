import type { ImportColumn } from '@/components/common/ExcelImportModal'
import type { EntityMeta, MetaAll } from '@/types'

/**
 * 由实体契约动态生成 Excel 导入列（与 EntityPage/AuditCenter 表单同源，避免两处维护）：
 * - kv 学分认定字段拆成「级别 / 等级」两列（如 竞赛级别/获奖等级），后端按规则矩阵核定
 * - select/cascader 列在「填表说明」工作表中附可选值
 * - 列标题与实体字段标签冲突时（如 inn_project 的 kv「承担角色」与 post 文本字段），
 *   kv 子列加「（认定）」后缀保证表头唯一，解析按表头精确匹配
 */
export function entityImportColumns(
  entity: EntityMeta | undefined,
  meta: MetaAll | null,
): ImportColumn[] {
  if (!entity || !meta) return []
  const labels = new Set(entity.fields.map((f) => f.label))
  const cols: ImportColumn[] = []
  for (const f of entity.fields) {
    if (f.type === 'kv') {
      const conf = meta.innovate_kv[f.kvCategory ?? '']
      if (!conf) continue
      const suffix = (t: string) => (labels.has(t) && t !== f.label ? `${t}（认定）` : t)
      cols.push({
        key: '_kv_chiefly',
        title: suffix(conf.chiefly_label),
        required: f.required,
        options: Object.keys(conf.kv),
      })
      const minors = [...new Set(Object.values(conf.kv).flatMap((m) => Object.keys(m)))]
      cols.push({
        key: '_kv_minor',
        title: suffix(conf.minor_label),
        required: f.required,
        example: `可选：${minors.join(' / ')}（须与${conf.chiefly_label}匹配，服务端按规则矩阵核定学分）`,
      })
      continue
    }
    cols.push({
      key: f.name,
      title: f.label,
      required: f.required,
      options: f.type === 'select'
        ? (meta as unknown as Record<string, string[] | undefined>)[f.options ?? '']
        : f.type === 'cascader'
          ? Object.keys((meta as unknown as Record<string, Record<string, string[]>>)[f.options ?? ''] ?? {})
          : undefined,
      example: f.type === 'number' ? '数字，如 10'
        : f.type === 'date' ? '日期，如 2025-07-01'
        : f.type === 'cascader' ? '填一级名称，具体职务填在「担任职务」列'
        : undefined,
    })
  }
  return cols
}
