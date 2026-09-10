import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Button, Card, Col, Row, Statistic, Table } from 'antd'
import { AuditOutlined, CheckCircleOutlined, RedoOutlined } from '@ant-design/icons'
import { auditAPI } from '@/api/modules'
import type { AuditSummaryItem } from '@/types'

const GROUP_LABEL: Record<string, string> = { inn: '创新创业', practice: '社会实践', other: '其他模块' }

export default function CounsellorDashboard() {
  const navigate = useNavigate()
  const [list, setList] = useState<AuditSummaryItem[]>([])
  const [totals, setTotals] = useState({ pending: 0, approved: 0 })

  const load = () => {
    auditAPI.summary()
      .then(({ list: l, pendingTotal, approvedTotal }) => {
        setList(l)
        setTotals({ pending: pendingTotal, approved: approvedTotal })
      })
      .catch(() => undefined)
  }
  useEffect(load, [])

  const columns = useMemo(() => [
    { title: '模块分组', dataIndex: 'group', width: 120, fixed: 'left' as const,
      render: (g: string) => GROUP_LABEL[g] ?? g },
    { title: '审核模块', dataIndex: 'label' },
    { title: '待审核数量', dataIndex: 'count', width: 120, render: (n: number) => n },
    { title: '操作', width: 100,
      render: (_: unknown, r: AuditSummaryItem) => (
        <Button type="link" size="small" onClick={() => navigate(`/audit?key=${r.key}`)}>前往审核</Button>
      ) },
  ], [navigate])

  return (
    <div>
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col xs={24} md={12}>
          <Card>
            <Statistic
              title="待审核事项"
              value={totals.pending}
              prefix={<AuditOutlined />}
              valueStyle={{ color: totals.pending > 0 ? '#cf1322' : undefined }}
              suffix="条"
            />
          </Card>
        </Col>
        <Col xs={24} md={12}>
          <Card>
            <Statistic
              title="累计已通过"
              value={totals.approved}
              prefix={<CheckCircleOutlined />}
              valueStyle={{ color: '#3f8600' }}
              suffix="条"
            />
          </Card>
        </Col>
      </Row>
      <Card
        title="待审核汇总"
        style={{ minWidth: 560 }}
        extra={<Button size="small" icon={<RedoOutlined />} onClick={load}>刷新</Button>}
      >
        <Table
          rowKey="key"
          size="small"
          pagination={false}
          dataSource={list}
          columns={columns as never}
        />
      </Card>
    </div>
  )
}
