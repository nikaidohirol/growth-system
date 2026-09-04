import { useEffect, useMemo, useState } from 'react'
import { Card, Col, Row, Statistic } from 'antd'
import { AuditOutlined, CheckCircleOutlined, TeamOutlined, UserOutlined } from '@ant-design/icons'
import EChart from '@/components/charts/EChart'
import type { EChartsOption } from 'echarts'
import { dashboardAPI } from '@/api/modules'
import type { DeanDashboardData } from '@/types'

export default function DeanDashboard() {
  const [data, setData] = useState<DeanDashboardData | null>(null)
  useEffect(() => {
    dashboardAPI.dean().then(setData).catch(() => undefined)
  }, [])

  const collegePie = useMemo<EChartsOption>(() => ({
    tooltip: { trigger: 'item' },
    legend: { bottom: 0, type: 'scroll' as const },
    series: [{
      type: 'pie', radius: ['35%', '60%'],
      data: data?.studentsByCollege ?? [],
    }],
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

  if (!data) return null
  return (
    <div>
      <Row gutter={16} style={{ marginBottom: 16 }}>
        {[
          { title: '全校学生', value: data.totalStudents, icon: <UserOutlined />, color: '#3b6fe0' },
          { title: '辅导员', value: data.totalCounsellors, icon: <TeamOutlined />, color: '#13c2c2' },
          { title: '待审核事项', value: data.pendingTotal, icon: <AuditOutlined />, color: '#cf1322' },
          { title: '累计认定通过', value: data.approvedTotal, icon: <CheckCircleOutlined />, color: '#3f8600' },
        ].map((s) => (
          <Col span={6} key={s.title}>
            <Card>
              <Statistic title={s.title} value={s.value} prefix={s.icon}
                         valueStyle={{ color: s.color }} />
            </Card>
          </Col>
        ))}
      </Row>
      <Row gutter={16}>
        <Col span={8}>
          <Card title="学生学院分布" size="small"><EChart option={collegePie} height={280} /></Card>
        </Col>
        <Col span={8}>
          <Card title="双创学分分布（按类别）" size="small"><EChart option={innBar} height={280} /></Card>
        </Col>
        <Col span={8}>
          <Card title="全校平均 GPA 趋势" size="small"><EChart option={gpaLine} height={280} /></Card>
        </Col>
      </Row>
    </div>
  )
}
