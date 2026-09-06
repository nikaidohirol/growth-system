import { useEffect, useMemo, useState } from 'react'
import { Card, Col, Row, Statistic } from 'antd'
import {
  AuditOutlined, CheckCircleOutlined, EyeOutlined, ScheduleOutlined, TeamOutlined, UserOutlined,
} from '@ant-design/icons'
import EChart from '@/components/charts/EChart'
import type { EChartsOption } from 'echarts'
import { dashboardAPI } from '@/api/modules'
import type { DeanDashboardData } from '@/types'

/** 院长看板：院系规模 + 待我终审/公示中监督 + 辅导员初审通过率（宏观监督，非逐条审批） */
export default function DeanDashboard() {
  const [data, setData] = useState<DeanDashboardData | null>(null)
  useEffect(() => {
    dashboardAPI.dean().then(setData).catch(() => undefined)
  }, [])

  const gradeBar = useMemo<EChartsOption>(() => ({
    tooltip: { trigger: 'axis' },
    grid: { left: 60, right: 20, bottom: 40 },
    xAxis: { type: 'category' as const, data: data?.studentsByGrade.map((x) => x.key) ?? [] },
    yAxis: { type: 'value' as const, name: '人数', minInterval: 1 },
    series: [{ type: 'bar', barMaxWidth: 48, itemStyle: { color: '#13c2c2', borderRadius: [4, 4, 0, 0] },
               data: data?.studentsByGrade.map((x) => x.value) ?? [] }],
  }), [data])

  const innBar = useMemo<EChartsOption>(() => ({
    tooltip: { trigger: 'axis' },
    grid: { left: 60, right: 20, bottom: 60 },
    xAxis: { type: 'category' as const, data: data?.innByCategory.map((x) => x.key) ?? [],
             axisLabel: { rotate: 30, fontSize: 10 } },
    yAxis: { type: 'value' as const, name: '认定总学分' },
    series: [{ type: 'bar', barMaxWidth: 36, itemStyle: { color: '#3b6fe0' },
               data: data?.innByCategory.map((x) => x.value) ?? [] }],
  }), [data])

  const gpaLine = useMemo<EChartsOption>(() => ({
    tooltip: { trigger: 'axis' },
    grid: { left: 50, right: 20, bottom: 40 },
    xAxis: { type: 'category' as const, data: data?.avgGpaTrend.map((x) => x.key) ?? [] },
    yAxis: { type: 'value' as const, min: (v: { min: number }) => Math.floor(v.min - 0.2) },
    series: [{ type: 'line', smooth: true, areaStyle: { opacity: 0.15 },
               data: data?.avgGpaTrend.map((x) => x.value) ?? [] }],
  }), [data])

  // 各辅导员初审通过率：条形图（tooltip 展示初审通过/已审总数），异常偏高/偏低一目了然
  const rateBar = useMemo<EChartsOption>(() => ({
    tooltip: {
      trigger: 'axis' as const,
      axisPointer: { type: 'shadow' as const },
      valueFormatter: (v) => `${v}%`,
      formatter: (params) => {
        const p = Array.isArray(params) ? params[0] : params
        const s = data?.counsellorStats.find((c) => c.name === p.name)
        return s ? `${p.name}<br/>初审通过率：${(s.rate * 100).toFixed(1)}%<br/>已审 ${s.total} 条（初审通过 ${s.passed}）`
                 : `${p.name}：暂无已审记录`
      },
    },
    grid: { left: 90, right: 50, top: 10, bottom: 30 },
    xAxis: { type: 'value' as const, max: 100, axisLabel: { formatter: '{value}%' } },
    yAxis: { type: 'category' as const, data: data?.counsellorStats.map((c) => c.name) ?? [] },
    series: [{ type: 'bar', barMaxWidth: 22,
               label: { show: true, position: 'right' as const, formatter: '{c}%' },
               itemStyle: { color: (p: { value?: unknown }) =>
                   (typeof p.value !== 'number' || p.value > 95 || p.value < 40 ? '#cf1322' : '#3f8600') },
               data: data?.counsellorStats.map((c) => Math.round(c.rate * 1000) / 10) ?? [] }],
  }), [data])

  if (!data) return null
  return (
    <div>
      <Row gutter={16} style={{ marginBottom: 16 }}>
        {[
          { title: '院系学生总数', value: data.totalStudents, icon: <UserOutlined />, color: '#3b6fe0' },
          { title: '院系辅导员', value: data.totalCounsellors, icon: <TeamOutlined />, color: '#13c2c2' },
          { title: '待审核事项', value: data.pendingTotal, icon: <AuditOutlined />, color: '#d46b08' },
          { title: '待我终审', value: data.deanPendingTotal, icon: <ScheduleOutlined />, color: '#cf1322' },
          { title: '公示中', value: data.publicTotal, icon: <EyeOutlined />, color: '#1677ff' },
          { title: '累计认定通过', value: data.approvedTotal, icon: <CheckCircleOutlined />, color: '#3f8600' },
        ].map((s) => (
          <Col span={4} key={s.title}>
            <Card>
              <Statistic title={s.title} value={s.value} prefix={s.icon}
                         valueStyle={{ color: s.color }} />
            </Card>
          </Col>
        ))}
      </Row>
      <Row gutter={16}>
        <Col span={8}>
          <Card title="院系学生年级分布" size="small"><EChart option={gradeBar} height={280} /></Card>
        </Col>
        <Col span={8}>
          <Card title="双创学分分布（按类别）" size="small"><EChart option={innBar} height={280} /></Card>
        </Col>
        <Col span={8}>
          <Card title="院系平均 GPA 趋势" size="small"><EChart option={gpaLine} height={280} /></Card>
        </Col>
      </Row>
      <Row gutter={16} style={{ marginTop: 16 }}>
        <Col span={24}>
          <Card title="辅导员初审通过率（宏观监督：异常偏高/偏低标红，可通过审核中心抽查）" size="small">
            {data.counsellorStats.length
              ? <EChart option={rateBar} height={Math.max(160, data.counsellorStats.length * 52)} />
              : <span style={{ color: '#999' }}>暂无已审记录</span>}
          </Card>
        </Col>
      </Row>
    </div>
  )
}
