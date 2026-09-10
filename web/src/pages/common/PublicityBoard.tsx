import { useCallback, useEffect, useState } from 'react'
import { App, Button, Card, Empty, Input, Modal, Radio, Space, Table, Tag, Typography } from 'antd'
import { CheckOutlined, CloseOutlined, EyeOutlined, SoundOutlined } from '@ant-design/icons'
import { objectionAPI } from '@/api/modules'
import { useAuthStore } from '@/store/auth'
import type { ObjectionItem, PublicityRow } from '@/types'

const OBJ_COLOR: Record<string, string> = { 待复核: 'gold', 成立: 'red', 不成立: 'green' }

/** 公示栏 — 公示期监督闭环：全院「公示中」记录公示 → 实名异议 → 院长复核（成立驳回 / 不成立维持）
 *  挂着「待复核」异议的记录暂停期满自动生效；复核结果双向通知异议人与被异议学生 */
export default function PublicityBoard() {
  const { message } = App.useApp()
  const { user } = useAuthStore()
  const isDean = user?.role === 'Dean'

  const [rows, setRows] = useState<PublicityRow[]>([])
  const [loading, setLoading] = useState(false)
  const [mine, setMine] = useState<ObjectionItem[]>([])
  const [objList, setObjList] = useState<ObjectionItem[]>([])
  const [objStatus, setObjStatus] = useState<'待复核' | '已复核'>('待复核')

  const [target, setTarget] = useState<PublicityRow | null>(null)
  const [reason, setReason] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [reviewing, setReviewing] = useState<{ item: ObjectionItem; result: '成立' | '不成立' } | null>(null)
  const [reviewOpinion, setReviewOpinion] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [pub, m] = await Promise.all([objectionAPI.publicity(), objectionAPI.mine()])
      setRows(pub.list)
      setMine(m.list)
      if (useAuthStore.getState().user?.role === 'Dean') {
        const lst = await objectionAPI.list({ status: objStatus === '待复核' ? '待复核' : '全部', pageSize: 50 })
        setObjList(objStatus === '待复核' ? lst.list : lst.list.filter((x) => x.status !== '待复核'))
      }
    } finally {
      setLoading(false)
    }
  }, [objStatus])  

  useEffect(() => { load().catch(() => undefined) }, [load])

  const submitObjection = async () => {
    if (!target) return
    if (reason.trim().length < 5) { message.warning('请填写异议理由（至少 5 个字），以便学院核实'); return }
    setSubmitting(true)
    try {
      await objectionAPI.submit({ key: target.key, recordId: target.recordId, reason: reason.trim() })
      message.success('异议已实名提交，学院将核实并在复核后向你反馈结果')
      setTarget(null); setReason('')
      await load()
    } finally {
      setSubmitting(false)
    }
  }

  const doReview = async () => {
    if (!reviewing) return
    if (reviewing.result === '不成立' && !reviewOpinion.trim()) {
      message.warning('维持认定时建议填写复核意见，便于异议人理解'); return
    }
    await objectionAPI.review(reviewing.item.id, reviewing.result, reviewOpinion.trim())
    message.success(reviewing.result === '成立'
      ? '已复核：异议成立，该认定记录已驳回并通知学生'
      : '已复核：异议不成立，认定维持，公示期满自动生效')
    setReviewing(null); setReviewOpinion('')
    await load()
  }

  const pubCols = [
    { title: '学生', key: 'stu', width: 150, fixed: 'left' as const, render: (_: unknown, r: PublicityRow) => (
      <span>{r.student.name}<span style={{ color: '#999', fontSize: 12, marginLeft: 6 }}>{r.student.classId}</span></span>
    ) },
    { title: '类别', dataIndex: 'label', key: 'label', width: 120 },
    { title: '认定内容', dataIndex: 'title', key: 'title', ellipsis: true },
    { title: '核定学分', dataIndex: 'credit', key: 'credit', width: 90,
      render: (v: number | null) => (v === null || v === undefined ? '-' : v) },
    { title: '公示截止', dataIndex: 'publicEnd', key: 'publicEnd', width: 170,
      render: (v: string) => v?.slice(0, 16) },
    { title: '操作', key: 'op', width: 110,
      render: (_: unknown, r: PublicityRow) => r.sid === user?.id ? (
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>本人记录</Typography.Text>
      ) : (
        <Button type="link" size="small" icon={<EyeOutlined />}
                onClick={() => { setTarget(r); setReason('') }}>
          提出异议
        </Button>
      ) },
  ]

  const objCols = (withOwner: boolean, withOp: boolean) => [
    ...(withOwner ? [{ title: '被异议学生', key: 'owner', width: 150, fixed: 'left' as const,
      render: (_: unknown, o: ObjectionItem) => o.owner ? (
        <span>{o.owner.name}<span style={{ color: '#999', fontSize: 12, marginLeft: 6 }}>{o.owner.classId}</span></span>
      ) : '-' }] : []),
    { title: '异议人', key: 'objector', width: 150, fixed: 'left' as const,
      render: (_: unknown, o: ObjectionItem) => (
        <span>{o.objector.name}<span style={{ color: '#999', fontSize: 12, marginLeft: 6 }}>{o.objector.uid}</span></span>
      ) },
    { title: '认定对象', key: 'target', render: (_: unknown, o: ObjectionItem) => (
      <span>{o.label}：<Typography.Text strong>{o.title}</Typography.Text></span>
    ) },
    { title: '异议理由', dataIndex: 'reason', key: 'reason' },
    { title: '提交时间', dataIndex: 'createdAt', key: 'createdAt', width: 165,
      render: (v: string) => v?.slice(0, 16) },
    { title: '状态', key: 'status', width: withOp ? 140 : 150,
      render: (_: unknown, o: ObjectionItem) => (
        <Space size={4} wrap>
          <Tag color={OBJ_COLOR[o.status]}>{o.status}</Tag>
          {o.status !== '待复核' && (
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              {o.handledBy} {o.handledTime?.slice(5, 16)}
            </Typography.Text>
          )}
        </Space>
      ) },
    ...(withOp ? [{ title: '操作', key: 'op', width: 240,
      render: (_: unknown, o: ObjectionItem) => o.status === '待复核' ? (
        <Space size={0}>
          <Button type="link" size="small" danger icon={<CloseOutlined />}
                  onClick={() => { setReviewing({ item: o, result: '成立' }); setReviewOpinion('') }}>
            异议成立·驳回
          </Button>
          <Button type="link" size="small" style={{ color: '#3f8600' }} icon={<CheckOutlined />}
                  onClick={() => { setReviewing({ item: o, result: '不成立' }); setReviewOpinion('') }}>
            不成立·维持
          </Button>
        </Space>
      ) : <span style={{ color: '#bbb' }}>已复核</span> }] : []),
  ]

  return (
    <div>
      {isDean && (
        <Card size="small" title={<span><EyeOutlined /> 异议复核</span>}
              style={{ marginBottom: 16, minWidth: 1130 }}
              extra={
                <Radio.Group value={objStatus} onChange={(e) => setObjStatus(e.target.value)} size="small">
                  <Radio.Button value="待复核">待复核</Radio.Button>
                  <Radio.Button value="已复核">已复核</Radio.Button>
                </Radio.Group>
              }>
          <Table rowKey="id" size="small" loading={loading} columns={objCols(true, true)}
                 dataSource={objList}
                 pagination={false} locale={{ emptyText: <Empty description="暂无待复核异议" /> }} />
        </Card>
      )}

      <Card size="small" title={<span><SoundOutlined /> 院级公示栏（公示期 {rows.length} 条）</span>}
            style={{ minWidth: 890 }}>
        <Typography.Paragraph type="secondary" style={{ marginBottom: 12, fontSize: 13 }}>
          公示期 7 天：认定结果公示接受全院师生监督，可对存疑记录实名提出异议（学院复核后反馈）；
          公示期满且无未复核异议的记录自动生效。
        </Typography.Paragraph>
        <Table rowKey={(r) => `${r.key}-${r.recordId}`} size="small" loading={loading}
               columns={pubCols} dataSource={rows} pagination={false}
               locale={{ emptyText: <Empty description="当前没有公示中的记录" /> }} />
      </Card>

      {!isDean && mine.length > 0 && (
        <Card size="small" title={`我提出的异议（${mine.length}）`} style={{ marginTop: 16, minWidth: 940 }}>
          <Table rowKey="id" size="small" columns={objCols(false, false)} dataSource={mine} pagination={false} />
        </Card>
      )}

      <Modal open={!!target} title={`实名异议 — ${target ? `${target.label}：${target.title}` : ''}`}
             okText="提交异议" onOk={submitObjection} confirmLoading={submitting}
             onCancel={() => setTarget(null)} okButtonProps={{ danger: true }}>
        <Typography.Paragraph type="secondary" style={{ fontSize: 13 }}>
          异议实名提交至学院，由院长复核：成立则撤销该认定，不成立则维持并反馈理由。
        </Typography.Paragraph>
        <Input.TextArea rows={4} value={reason} onChange={(e) => setReason(e.target.value)}
                        maxLength={300} showCount
                        placeholder="请说明存疑点（如材料与证书不符、学分折算有误、人员次序存疑等），至少 5 个字" />
      </Modal>

      <Modal open={!!reviewing} title={`复核公示异议 — ${reviewing ? reviewing.item.title : ''}`}
             okText="确认复核结论" onOk={doReview} onCancel={() => setReviewing(null)}
             okButtonProps={reviewing?.result === '成立' ? { danger: true } : undefined}>
        {reviewing && (
          <>
            <Typography.Paragraph type="secondary" style={{ fontSize: 13 }}>
              异议人 {reviewing.item.objector.name}（{reviewing.item.objector.uid}）：
              {reviewing.item.reason}
            </Typography.Paragraph>
            <Radio.Group value={reviewing.result}
                         onChange={(e) => setReviewing({ ...reviewing, result: e.target.value })}
                         style={{ marginBottom: 12 }}>
              <Radio value="成立">异议成立，撤销认定（记录驳回，学生可修改重报）</Radio>
              <Radio value="不成立">异议不成立，维持认定（公示期满自动生效）</Radio>
            </Radio.Group>
            <Input.TextArea rows={3} value={reviewOpinion} onChange={(e) => setReviewOpinion(e.target.value)}
                            maxLength={200} showCount placeholder="复核意见（反馈给异议人与被异议学生）" />
          </>
        )}
      </Modal>
    </div>
  )
}
