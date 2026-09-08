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
      label: { formatter: '{b}\n{c} 学分' },
      data: pandect?.innCreditList.filter((x) => x.value > 0) ?? [],
    }],
  }), [pandect])

  const praPie = useMemo<EChartsOption>(() => ({
    tooltip: { trigger: 'item', formatter: '{b}: {c} 学分 ({d}%)' },
    legend: { bottom: 0 },
    series: [{
      type: 'pie', radius: ['38%', '62%'],
      data: pandect?.practiceCreditList.filter((x) => x.value > 0) ?? [],
    }],
  }), [pandect])

  if (!pandect) return null
  const r = pandect.rules
  const pct = (v: number, min: number) => Math.min(100, Math.round((v / min) * 100))

  return (
    <div>
      <Card style={{ marginBottom: 16 }}>
        <Statistic
          title={`你好，${user?.name}同学`}
          value="欢迎回来"
          suffix={
            <Button size="small" icon={<RedoOutlined />} onClick={load} style={{ marginLeft: 12 }}>
              刷新
            </Button>
          }
        />
      </Card>

      <Row gutter={16} style={{ marginBottom: 16 }}>
        {[
          { title: '创新创业学分', value: pandect.innCredit, min: r.min_inn, color: '#3b6fe0' },
          { title: '社会实践学分', value: pandect.praCredit, min: r.min_pra, color: '#52c41a' },
          { title: '总学分', value: pandect.sumCredit, min: r.min_sum, color: '#722ed1' },
        ].map((s) => (
          <Col span={8} key={s.title}>
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
        <Col span={14}>
          <Card title="创新创业学分构成" size="small">
            <EChart option={innPie} height={280} />
          </Card>
        </Col>
        <Col span={10}>
          <Card title="社会实践学分构成" size="small">
            <EChart option={praPie} height={280} />
          </Card>
        </Col>
      </Row>

      <Card title="驳回提醒" size="small" extra={<span style={{ color: '#999', fontSize: 12 }}>
        共 {backs.length} 条被驳回，可修改后重新提交
      </span>}>
        <Table
          rowKey={(r) => r.key + r.id}
          size="small"
          pagination={false}
          dataSource={backs}
          columns={[
            { title: '模块', dataIndex: 'label', width: 140,
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
