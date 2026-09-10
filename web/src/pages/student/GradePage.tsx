import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { Card, Col, Empty, Row, Table, Tag, Tooltip, Typography } from 'antd'
import type { TableColumnsType } from 'antd'
import EChart from '@/components/charts/EChart'
import type { EChartsOption } from 'echarts'
import { compAPI, gpaAPI } from '@/api/modules'
import { useMetaStore } from '@/store/meta'
import type { CompBonusItem, CompForecast, GpaRow } from '@/types'

const { Text } = Typography

/** 维度汇总：基准/学业分 + 明细加分（封顶提示） */
function dimRows(f: CompForecast) {
  return [
    {
      dim: '学业',
      score: f.academic.score,
      note: f.academic.gpa != null
        ? `最近学期 GPA ${f.academic.gpa}（${f.academic.semester}）×换算系数`
        : '暂无 GPA 数据',
      items: [] as CompBonusItem[],
    },
    {
      dim: '德育',
      score: f.moral.score,
      note: `基准分 ${f.moral.base} + 加分 ${Number((f.moral.score - f.moral.base).toFixed(2))}`,
      items: f.moral.items,
    },
    {
      dim: '文体',
      score: f.sports.score,
      note: `基准分 ${f.sports.base} + 加分 ${Number((f.sports.score - f.sports.base).toFixed(2))}`,
      items: f.sports.items,
    },
    {
      dim: '创新加分',
      score: f.innovation.bonus,
      note: f.innovation.capped ? '已达封顶，超出部分不计入' : '创新学分（规则矩阵核定）直接计入',
      items: f.innovation.items,
    },
  ]
}

const DIM_COLOR: Record<string, string> = {
  学业: 'blue', 德育: 'green', 文体: 'orange', 创新加分: 'purple',
}

interface TraceRow { dim: string; item: CompBonusItem | null; note: string }

const traceColumns: TableColumnsType<TraceRow> = [
  { title: '维度', dataIndex: 'dim', width: 110, fixed: 'left' as const,
    render: (dim: string) => <Tag color={DIM_COLOR[dim]}>{dim}</Tag> },
  { title: '来源明细（点击追溯）', key: 'item',
    render: (_, r) => r.item
      ? <Link to={`/entity/${r.item.key}`}>{r.item.label}</Link>
      : <Text type="secondary">{r.note}</Text> },
  { title: '加分', dataIndex: 'item', key: 'score', width: 90, align: 'right',
    render: (_, r) => (r.item ? `+${r.item.score}` : '') },
]

export default function GradePage() {
  const [rows, setRows] = useState<GpaRow[]>([])
  const [fc, setFc] = useState<CompForecast | null>(null)
  const { meta } = useMetaStore()
  useEffect(() => {
    gpaAPI.my().then(setRows).catch(() => undefined)
    compAPI.me().then(setFc).catch(() => undefined)
  }, [])

  const trend = useMemo<EChartsOption>(() => ({
    tooltip: { trigger: 'axis' },
    legend: { bottom: 0 },
    grid: { left: 50, right: 44, bottom: 50 },
    xAxis: { type: 'category' as const, data: rows.map((r) => r.semester) },
    yAxis: [{ type: 'value' as const, name: 'GPA', min: (v: { min: number }) => Math.floor(v.min - 0.2) },
            { type: 'value' as const, name: '分数', max: 100 }],
    series: [
      { name: 'GPA', type: 'line', smooth: true, data: rows.map((r) => r.gpa) },
      { name: '综测成绩', type: 'line', yAxisIndex: 1, smooth: true, data: rows.map((r) => r.comp) },
    ],
  }), [rows])

  const rankBar = useMemo<EChartsOption>(() => ({
    tooltip: { trigger: 'axis' },
    grid: { left: 50, right: 24, bottom: 50 },
    xAxis: { type: 'category' as const, data: rows.map((r) => r.semester) },
    yAxis: { type: 'value' as const, name: '名次（小更好）', inverse: true,
             nameLocation: 'start' as const, nameGap: 14,
             nameTextStyle: { align: 'left' as const } },
    series: [
      { name: 'GPA 排名', type: 'bar', barMaxWidth: 26, data: rows.map((r) => r.gpaRank) },
      { name: '综测排名', type: 'bar', barMaxWidth: 26, data: rows.map((r) => r.compRank) },
    ],
  }), [rows])

  const w = meta?.comp_rule?.weights
  const innCap = meta?.comp_rule?.innovation?.cap
  const ruleText = w
    ? `总分 = 学业×${w.academic} + 德育×${w.moral} + 文体×${w.sports}` +
      (innCap != null ? ` + 创新加分（封顶 ${innCap}）` : '')
    : '总分 = 学业×0.7 + 德育×0.2 + 文体×0.1 + 创新加分'

  return (
    <>
      <Row gutter={16}>
        <Col xs={24} md={10}>
          <Card title="各学期成绩" size="small" style={{ minWidth: 430 }}>
            <Table
              rowKey="id" size="small" pagination={false} dataSource={rows}
              columns={[
                { title: '学期', dataIndex: 'semester', fixed: 'left' as const },
                { title: 'GPA', dataIndex: 'gpa' },
                { title: '综测', dataIndex: 'comp' },
                { title: '排名', key: 'rank',
                  render: (_, r: GpaRow) => `${r.gpaRank} / ${r.maxRank}` },
              ]}
            />
          </Card>
        </Col>
        {/* 成绩趋势/专业排名属次要图表：小屏隐藏（xs=0），只留各学期成绩与综测测算 */}
        <Col xs={0} md={14}>
          <Card title="成绩趋势" size="small" style={{ marginBottom: 16 }}>
            <EChart option={trend} height={240} />
          </Card>
          <Card title="专业排名" size="small">
            <EChart option={rankBar} height={220} />
          </Card>
        </Col>
      </Row>
      <Card
        size="small" style={{ marginTop: 16, minWidth: 560 }}
        title="综测过程分测算（系统实时 · 仅统计已生效记录）"
        extra={<Tooltip title={ruleText}><Text type="secondary">测算口径</Text></Tooltip>}
      >
        {fc ? (
          <>
            <Row gutter={16} style={{ marginBottom: 12 }}>
              <Col xs={12} md={5}>
                <StatisticLike label="测算总分" value={fc.total} strong />
              </Col>
              <Col xs={12} md={5}>
                <StatisticLike label="专业内排名"
                  value={fc.majorSize ? `${fc.majorRank} / ${fc.majorSize}` : '—'}
                  note="按同年级同专业完整名单测算" />
              </Col>
              <Col xs={12} md={4}><StatisticLike label="学业" value={fc.academic.score} /></Col>
              <Col xs={12} md={4}><StatisticLike label="德育" value={fc.moral.score} /></Col>
              <Col xs={12} md={3}><StatisticLike label="文体" value={fc.sports.score} /></Col>
              <Col xs={12} md={3}>
                <StatisticLike label="创新加分" value={`+${fc.innovation.bonus}`}
                  note={fc.imported ? `教务综测 ${fc.imported.comp}（第 ${fc.imported.compRank}/${fc.imported.maxRank}）` : undefined} />
              </Col>
            </Row>
            <Table
              rowKey={(r) => `${r.dim}-${r.item?.recordId ?? 'sum'}`} size="small"
              pagination={false}
              dataSource={dimRows(fc).flatMap((d): TraceRow[] =>
                d.items.length
                  ? d.items.map((it) => ({ dim: d.dim, item: it, note: '' }))
                  : [{ dim: d.dim, item: null, note: d.note }])}
              columns={traceColumns}
            />
            {fc.imported && (
              <Text type="secondary" style={{ display: 'block', marginTop: 8 }}>
                教务导入的综测成绩为学院线下评定后的权威结果，与系统测算过程分并存对照，两者不一致时以教务为准。
              </Text>
            )}
          </>
        ) : (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无测算数据（需存在已生效的记录）" />
        )}
      </Card>
    </>
  )
}

/** 轻量数值块（避免引入 Statistic 的固定样式导致行高不齐） */
function StatisticLike({ label, value, note, strong }: {
  label: string; value: string | number; note?: string; strong?: boolean
}) {
  return (
    <div>
      <Text type="secondary" style={{ fontSize: 12 }}>{label}</Text>
      <div style={{ fontSize: strong ? 26 : 20, fontWeight: strong ? 700 : 600, lineHeight: 1.3 }}>
        {value}
      </div>
      {note && <Text type="secondary" style={{ fontSize: 12 }}>{note}</Text>}
    </div>
  )
}
