import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Button, Card, Col, Progress, Row, Statistic, Table, Tag } from 'antd'
import { RedoOutlined } from '@ant-design/icons'
import EChart from '@/components/charts/EChart'
import type { EChartsOption } from 'echarts'
import { dashboardAPI } from '@/api/modules'
import { useAuthStore } from '@/store/auth'
import type { BackItem, Pandect } from '@/types'

export default function StudentDashboard() {
  const navigate = useNavigate()
  const user = useAuthStore((s) => s.user)
  const [pandect, setPandect] = useState<Pandect | null>(null)
  const [backs, setBacks] = useState<BackItem[]>([])

  const load = () => {
    dashboardAPI.pandect().then(setPandect).catch(() => undefined)
    dashboardAPI.backlist().then(setBacks).catch(() => undefined)
  }
  useEffect(load, [])

  const innPie = useMemo<EChartsOption>(() => ({
    tooltip: { trigger: 'item', formatter: '{b}: {c} 学分 ({d}%)' },
    legend: { bottom: 0, type: 'scroll' as const },
    series: [{
      type: 'pie', radius: ['38%', '62%'],
      label: { formatter: '{c} 学分' },
      data: (pandect?.innCreditList ?? []).filter((x) => x.value > 0)
        .map((x) => ({ name: x.key, value: x.value })),
    }],
  }), [pandect])

  const praPie = useMemo<EChartsOption>(() => ({
    tooltip: { trigger: 'item', formatter: '{b}: {c} 学分 ({d}%)' },
    legend: { bottom: 0, type: 'scroll' as const },
    series: [{
      type: 'pie', radius: ['38%', '62%'],
      label: { formatter: '{c} 学分' },
      data: (pandect?.practiceCreditList ?? []).filter((x) => x.value > 0)
        .map((x) => ({ name: x.key, value: x.value })),
    }],
  }), [pandect])

  if (!pandect) return null
  const r = pandect.rules
  const pct = (v: number, min: number) => Math.min(100, Math.round((v / min) * 100))

  const hour = new Date().getHours()
  const greeting = hour < 6 ? '凌晨好' : hour < 12 ? '早上好' : hour < 14 ? '中午好' : hour < 18 ? '下午好' : '晚上好'
  const today = new Date().toLocaleDateString('zh-CN', { year: 'numeric', month: 'long', day: 'numeric', weekday: 'long' })

  return (
    <div>
      <Card
        style={{
          marginBottom: 16, border: 'none',
          background: 'linear-gradient(120deg, #4c6ef5 0%, #748ffc 60%, #91a7ff 100%)',
        }}
        styles={{ body: { padding: '22px 24px' } }}
      >
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div>
            <div style={{ color: '#fff', fontSize: 20, fontWeight: 600 }}>
              {greeting}，{user?.name}{{ Student: '同学', Counsellor: '老师', Dean: '院长' }[user?.role ?? 'Student']}
            </div>
            <div style={{ color: 'rgba(255,255,255,0.78)', fontSize: 13, marginTop: 6 }}>
              今天是 {today}，祝你学习顺利
            </div>
          </div>
          <Button ghost icon={<RedoOutlined />} onClick={load}>
            刷新
          </Button>
        </div>
      </Card>

      <Row gutter={16} style={{ marginBottom: 16 }}>
        {[
          { title: '创新创业学分', value: pandect.innCredit, min: r.min_inn, color: '#3b6fe0' },
          { title: '社会实践学分', value: pandect.praCredit, min: r.min_pra, color: '#52c41a' },
          { title: '总学分', value: pandect.sumCredit, min: r.min_sum, color: '#722ed1' },
        ].map((s) => (
          <Col xs={24} md={8} key={s.title}>
            <Card>
              <Statistic title={s.title} value={s.value} precision={2} suffix={`/ ${s.min} 学分`} />
              <Progress
                percent={pct(s.value, s.min)}
                strokeColor={s.color}
                status={s.value >= s.min ? 'success' : 'active'}
                format={() => (s.value >= s.min ? '已达标' : `还差 ${(s.min - s.value).toFixed(2)}`)}
                style={{ marginTop: 12 }}
              />
            </Card>
          </Col>
        ))}
      </Row>

      <Row gutter={16} style={{ marginBottom: 16 }}>
        {/* 学分构成饼图属次要信息：小屏隐藏（xs=0），中屏起各占一半 */}
        <Col xs={0} md={12}>
          <Card title="创新创业学分构成" size="small">
            <EChart option={innPie} height={280} />
          </Card>
        </Col>
        {/* 学分构成饼图属次要信息：小屏隐藏（xs=0），中屏起各占一半 */}
        <Col xs={0} md={12}>
          <Card title="社会实践学分构成" size="small">
            <EChart option={praPie} height={280} />
          </Card>
        </Col>
      </Row>

      <Card title="驳回提醒" size="small" style={{ minWidth: 800 }} extra={<span style={{ color: '#999', fontSize: 12 }}>
        共 {backs.length} 条被驳回，可修改后重新提交
      </span>}>
        <Table
          rowKey={(r) => r.key + r.id}
          size="small"
          pagination={false}
          dataSource={backs}
          columns={[
            { title: '模块', dataIndex: 'label', width: 140, fixed: 'left' as const,
              render: (v, r: BackItem) => (
                <a onClick={() => navigate(`/entity/${r.key}`)}>{v}</a>
              ) },
            { title: '内容', dataIndex: 'title', ellipsis: true },
            { title: '驳回原因', dataIndex: 'opinion', ellipsis: true,
              render: (v) => <Tag color="red">{v}</Tag> },
            { title: '时间', dataIndex: 'auditTime', width: 170 },
            { title: '', key: 'go', width: 90,
              render: (_, r: BackItem) => (
                <Button type="link" size="small" onClick={() => navigate(`/entity/${r.key}`)}>
                  去修改
                </Button>
              ) },
          ]}
          locale={{ emptyText: '太棒了，暂无驳回记录' }}
        />
      </Card>
    </div>
  )
}
