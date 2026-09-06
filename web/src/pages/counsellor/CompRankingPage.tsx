import { useCallback, useEffect, useMemo, useState } from 'react'
import { Button, Card, message, Select, Space, Table, Tag, Tooltip, Typography } from 'antd'
import { DownloadOutlined, ReloadOutlined } from '@ant-design/icons'
import * as XLSX from 'xlsx'
import dayjs from 'dayjs'
import { compAPI } from '@/api/modules'
import { useAuthStore } from '@/store/auth'
import { useMetaStore } from '@/store/meta'
import type { CompForecast } from '@/types'

const { Text } = Typography

// ---- 导出：成绩单汇总 Excel（沿用项目纯前端 xlsx 生成惯例，与 ExcelImportModal 对称）----
const EXPORT_HEADER = ['排名', '学号', '姓名', '班级', '年级', '专业', '测算总分',
  '学业分', 'GPA', '德育分', '文体分', '创新加分', '教务综测', '教务综测排名']

const toRows = (lst: CompForecast[]) => lst.map((r) => ({
  '排名': r.majorRank, '学号': r.uid, '姓名': r.name,
  '班级': r.classId ?? '未分班', '年级': r.periods ?? '', '专业': r.major ?? '',
  '测算总分': r.total, '学业分': r.academic.score, 'GPA': r.academic.gpa ?? '',
  '德育分': r.moral.score, '文体分': r.sports.score, '创新加分': r.innovation.bonus,
  '教务综测': r.imported?.comp ?? '未导入',
  '教务综测排名': r.imported ? `${r.imported.compRank}/${r.imported.maxRank}` : '未导入',
}))

const sheetCols = EXPORT_HEADER.map((h) => ({ wch: Math.max(8, h.length * 2 + 2) }))

const noteSheet = (wb: XLSX.WorkBook, scope: string, n: number) => {
  const ws = XLSX.utils.aoa_to_sheet([
    ['综测测算汇总（系统过程分）'],
    [`范围：${scope}　人数：${n}　导出时间：${dayjs().format('YYYY-MM-DD HH:mm')}`],
    ['口径：总分 = 学业×0.7 + 德育×0.2 + 文体×0.1 + 创新加分（封顶 6）；仅统计已生效记录'],
    ['排名：同年级同专业内总分从高到低顺序编号（评奖/保研口径）'],
    ['对照：教务综测为学院线下评定后报教务的权威结果，与系统测算并存，不一致以教务为准'],
  ])
  XLSX.utils.book_append_sheet(wb, ws, '导出说明')
}

/** 综测测算专业排名表：同年级同专业口径，系统过程分与教务导入综测并列对照
 *  默认锁定某年级×某专业（避免全院混排），可按年级/专业组合切换；排名为总分从高到低顺序编号 */
export default function CompRankingPage() {
  const [list, setList] = useState<CompForecast[]>([])
  const [loading, setLoading] = useState(false)
  const [exporting, setExporting] = useState(false)
  const { meta } = useMetaStore()
  const { user } = useAuthStore()
  const isDean = user?.role === 'Dean'

  // 年级/专业选项取自系统字典（全量可选，不依赖已加载数据）
  const periodOptions = useMemo(
    () => (meta?.periods ?? []).map((p) => ({ value: p, label: p })), [meta])
  const majorOptions = useMemo(
    () => [...new Set(Object.values(meta?.college_major ?? {}).flat())]
      .map((m) => ({ value: m, label: m })), [meta])

  const [major, setMajor] = useState<string | undefined>()
  const [periods, setPeriods] = useState<string | undefined>()
  const [nonce, setNonce] = useState(0)   // 手动刷新计数
  // 默认选中第一组（2023级×字典第一个专业），打开页面即是单组榜单
  useEffect(() => {
    if (!meta) return
    setPeriods((p) => p ?? meta.periods[0])
    setMajor((m) => m ?? Object.values(meta.college_major)[0]?.[0])
  }, [meta])

  // 字典就绪后才请求（保证默认锁定单组）；major/periods 变化或手动刷新时重查
  const fetchList = useCallback(async (m: string, p: string) => {
    setLoading(true)
    try {
      const d = await compAPI.list({ major: m, periods: p })
      setList(d.list)
    } finally {
      setLoading(false)
    }
  }, [])
  useEffect(() => {
    if (major && periods) fetchList(major, periods)
  }, [major, periods, fetchList, nonce])

  /** 导出当前筛选组的成绩单汇总（单 Sheet） */
  const exportCurrent = () => {
    if (!major || !periods || !list.length) return
    const wb = XLSX.utils.book_new()
    noteSheet(wb, `${periods} ${major}`, list.length)
    const ws = XLSX.utils.json_to_sheet(toRows(list), { header: EXPORT_HEADER })
    ws['!cols'] = sheetCols
    XLSX.utils.book_append_sheet(wb, ws, `${periods}${major}`)
    XLSX.writeFile(wb, `综测测算_${periods}${major}_${dayjs().format('YYYYMMDD')}.xlsx`)
    message.success('已导出当前组成绩单汇总')
  }

  /** 院长：导出全院成绩单汇总（每个年级×专业一个 Sheet，一次请求取全量） */
  const exportAll = async () => {
    setExporting(true)
    try {
      const d = await compAPI.list()
      const wb = XLSX.utils.book_new()
      noteSheet(wb, '全院（按年级×专业分 Sheet）', d.list.length)
      const groups = new Map<string, CompForecast[]>()
      for (const r of d.list) {
        const k = `${r.periods ?? '未分年级'}${r.major ?? '未分专业'}`
        const arr = groups.get(k)
        if (arr) arr.push(r)
        else groups.set(k, [r])
      }
      for (const [k, arr] of groups) {
        arr.sort((a, b) => a.majorRank - b.majorRank)
        const ws = XLSX.utils.json_to_sheet(toRows(arr), { header: EXPORT_HEADER })
        ws['!cols'] = sheetCols
        XLSX.utils.book_append_sheet(wb, ws, k)
      }
      XLSX.writeFile(wb, `综测测算汇总_全院_${dayjs().format('YYYYMMDD')}.xlsx`)
      message.success(`已导出全院汇总（${groups.size} 个年级×专业，共 ${d.list.length} 人）`)
    } finally {
      setExporting(false)
    }
  }

  // 默认按 年级→专业→排名 展示（排名即总分从高到低）
  const sorted = useMemo(() => [...list].sort((a, b) =>
    (a.periods ?? '').localeCompare(b.periods ?? '') ||
    (a.major ?? '').localeCompare(b.major ?? '') || a.majorRank - b.majorRank), [list])

  return (
    <Card
      title="综测测算排名（系统过程分 · 同年级同专业口径）"
      extra={
        <Space>
          <Select
            placeholder="按年级筛选" style={{ width: 130 }}
            value={periods} options={periodOptions}
            onChange={(v) => setPeriods(v)}
          />
          <Select
            placeholder="按专业筛选" style={{ width: 200 }}
            value={major} options={majorOptions}
            onChange={(v) => setMajor(v)}
          />
          {isDean && (
            <Button icon={<DownloadOutlined />} loading={exporting} onClick={exportAll}>
              导出全院汇总
            </Button>
          )}
          <Button icon={<DownloadOutlined />} disabled={!list.length} onClick={exportCurrent}>
            导出当前组
          </Button>
          <ReloadOutlined onClick={() => setNonce((n) => n + 1)} />
        </Space>
      }
    >
      <Tooltip title="总分 = 学业×0.7 + 德育×0.2 + 文体×0.1 + 创新加分（封顶 6）；只统计已生效记录">
        <Text type="secondary" style={{ display: 'block', marginBottom: 12 }}>
          测算口径：学业×70% + 德育×20% + 文体×10% + 创新加分 · 排名范围同年级同专业（评奖/保研口径），总分从高到低顺序编号 · 与教务导入综测并存对照
        </Text>
      </Tooltip>
      {/* key 绑定筛选组合：切换年级/专业时强制重挂载，分页器自动回到第 1 页 */}
      <Table
        key={`${periods}-${major}`}
        rowKey="sid" size="small" loading={loading} dataSource={sorted}
        pagination={{ pageSize: 20, showTotal: (t) => `共 ${t} 人` }}
        columns={[
          { title: '排名', dataIndex: 'majorRank', width: 70, align: 'right',
            render: (v: number, r: CompForecast) =>
              <Text strong>{r.majorSize ? v : '—'}</Text> },
          { title: '年级', dataIndex: 'periods', width: 90,
            render: (v: string | null) => v || '—' },
          { title: '专业', dataIndex: 'major', width: 170,
            render: (v: string | null) => v || '—' },
          { title: '班级', dataIndex: 'classId', width: 110,
            render: (v: string | null) => v || '未分班' },
          { title: '学号', dataIndex: 'uid', width: 110 },
          { title: '姓名', dataIndex: 'name', width: 90 },
          { title: '测算总分', key: 'total', width: 90, align: 'right',
            render: (_, r: CompForecast) =>
              <Text strong>{r.total}</Text> },
          { title: '学业', key: 'academic', width: 110, align: 'right',
            render: (_, r: CompForecast) => r.academic.gpa != null
              ? `${r.academic.score}（GPA ${r.academic.gpa}）` : '—' },
          { title: '德育', key: 'moral', width: 80, align: 'right',
            render: (_, r: CompForecast) => r.moral.score },
          { title: '文体', key: 'sports', width: 80, align: 'right',
            render: (_, r: CompForecast) => r.sports.score },
          { title: '创新加分', key: 'inn', width: 90, align: 'right',
            render: (_, r: CompForecast) =>
              `+${r.innovation.bonus}${r.innovation.capped ? '（封顶）' : ''}` },
          { title: '教务综测', key: 'imported', width: 130, align: 'right',
            render: (_, r: CompForecast) => r.imported
              ? <Tag>{r.imported.comp}（第 {r.imported.compRank}/{r.imported.maxRank}）</Tag>
              : <Text type="secondary">未导入</Text> },
        ]}
      />
    </Card>
  )
}
