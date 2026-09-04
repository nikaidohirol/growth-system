import { useEffect, useMemo, useState } from 'react'
import { Card, Col, Row, Table } from 'antd'
import EChart from '@/components/charts/EChart'
import type { EChartsOption } from 'echarts'
import { gpaAPI } from '@/api/modules'
import type { GpaRow } from '@/types'

export default function GradePage() {
  const [rows, setRows] = useState<GpaRow[]>([])
  useEffect(() => {
    gpaAPI.my().then(setRows).catch(() => undefined)
  }, [])

  const trend = useMemo<EChartsOption>(() => ({
    tooltip: { trigger: 'axis' },
    legend: { bottom: 0 },
    grid: { left: 50, right: 24, bottom: 50 },
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
    yAxis: { type: 'value' as const, name: '名次（小更好）', inverse: true },
    series: [
      { name: 'GPA 排名', type: 'bar', barMaxWidth: 26, data: rows.map((r) => r.gpaRank) },
      { name: '综测排名', type: 'bar', barMaxWidth: 26, data: rows.map((r) => r.compRank) },
    ],
  }), [rows])

  return (
    <Row gutter={16}>
      <Col span={10}>
        <Card title="各学期成绩" size="small">
          <Table
            rowKey="id" size="small" pagination={false} dataSource={rows}
            columns={[
              { title: '学期', dataIndex: 'semester' },
              { title: 'GPA', dataIndex: 'gpa' },
              { title: '综测', dataIndex: 'comp' },
              { title: '排名', key: 'rank',
                render: (_, r: GpaRow) => `${r.gpaRank} / ${r.maxRank}` },
            ]}
          />
        </Card>
      </Col>
      <Col span={14}>
        <Card title="成绩趋势" size="small" style={{ marginBottom: 16 }}>
          <EChart option={trend} height={240} />
        </Card>
        <Card title="专业排名" size="small">
          <EChart option={rankBar} height={220} />
        </Card>
      </Col>
    </Row>
  )
}
