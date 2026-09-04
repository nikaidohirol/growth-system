import { useCallback, useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import {
  App, Button, Card, Image, Input, Modal, Segmented, Select, Space, Table, Tag,
} from 'antd'
import { CheckOutlined, CloseOutlined, RedoOutlined, RobotOutlined } from '@ant-design/icons'
import { aiAPI, auditAPI } from '@/api/modules'
import { useMetaStore } from '@/store/meta'
import type { EntityMeta, EntityRecord } from '@/types'

const STATUS_COLOR: Record<string, string> = { 待审核: 'gold', 通过: 'green', 驳回: 'red' }
const GROUP_LABEL: Record<string, string> = { inn: '创新创业', practice: '社会实践', other: '荣誉与其他' }

type AuditRow = EntityRecord & {
  student: { uid: string; name: string; classId?: string; college?: string }
}

/** 审核中心：注册表驱动的统一审核界面（AI 建议 + 通过/驳回） */
export default function AuditCenter() {
  const { message } = App.useApp()
  const [params] = useSearchParams()
  const { entities, entityByKey, loaded, load } = useMetaStore()

  const groups = useMemo(() => ['inn', 'practice', 'other'] as const, [])
  const [group, setGroup] = useState<string>(
    () => entityByKey(params.get('key') ?? '')?.group ?? 'inn')
  const [activeKey, setActiveKey] = useState<string>(
    () => params.get('key') ?? entities.find((e) => e.group === 'inn')?.key ?? 'inn_chair')

  const [rows, setRows] = useState<AuditRow[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(10)
  const [status, setStatus] = useState('待审核')
  const [keyword, setKeyword] = useState('')
  const [loading, setLoading] = useState(false)
  const [detail, setDetail] = useState<AuditRow | null>(null)
  const [rejecting, setRejecting] = useState<AuditRow | null>(null)
  const [reason, setReason] = useState('')
  const [aiTip, setAiTip] = useState<{ suggestion: string; reason: string } | null>(null)
  const [aiLoading, setAiLoading] = useState(false)

  useEffect(() => {
    if (!loaded) load().catch(() => undefined)
  }, [loaded, load])

  const entity = entityByKey(activeKey)

  const loadRows = useCallback(async (p = page, ps = pageSize) => {
    if (!activeKey) return
    setLoading(true)
    try {
      const data = await auditAPI.records({ key: activeKey, status, page: p, pageSize: ps, keyword })
      setRows(data.list)
      setTotal(data.total)
    } finally {
      setLoading(false)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeKey, status, keyword, page, pageSize])

  useEffect(() => {
    if (loaded && entity) loadRows()
  }, [loaded, entity, page, pageSize]) // eslint-disable-line react-hooks/exhaustive-deps

  const submit = async (r: AuditRow, result: '通过' | '驳回', opinion: string) => {
    await auditAPI.submit(activeKey, r.id, result, opinion)
    message.success(`已${result}`)
    setDetail(null)
    setRejecting(null)
    loadRows()
  }

  const askAI = async (r: AuditRow) => {
    setAiLoading(true)
    setAiTip(null)
    try {
      const item: Record<string, unknown> = { student: r.student }
      for (const f of entity?.fields ?? []) item[f.name] = (r as unknown as Record<string, unknown>)[f.name]
      setAiTip(await aiAPI.auditAssist(activeKey, item))
    } catch { /* 503 离线 */ } finally {
      setAiLoading(false)
    }
  }

  const groupEntities = entities.filter((e) => e.group === group)

  const columns = useMemo(() => {
    if (!entity) return []
    return [
      { title: '学生', key: 'stu', width: 150, fixed: 'left' as const,
        render: (_: unknown, r: AuditRow) => (
          <div>
            <div>{r.student.name} <Tag style={{ marginLeft: 4 }}>{r.student.uid}</Tag></div>
            <span style={{ color: '#999', fontSize: 12 }}>{r.student.classId} {r.student.college}</span>
          </div>
        ) },
      ...entity.fields.filter((f) => f.inTable).map((f) => ({
        title: f.label, dataIndex: f.name, key: f.name, ellipsis: true,
        render: (v: unknown) => (v ? String(v).replace('·', ' / ') : '-'),
      })),
      { title: '材料', dataIndex: 'files', width: 90,
        render: (files: AuditRow['files']) => (files?.length
          ? <Image.PreviewGroup>{files.map((f) => (
            <Image key={f.url} src={f.url} width={36} height={36} style={{ objectFit: 'cover', borderRadius: 4 }} />
          ))}</Image.PreviewGroup>
          : <Tag>无</Tag>) },
      { title: '状态', dataIndex: 'status', width: 84,
        render: (s: string) => <Tag color={STATUS_COLOR[s]}>{s}</Tag> },
      { title: '操作', key: 'op', width: 210, fixed: 'right' as const,
        render: (_: unknown, r: AuditRow) => (
          <Space size={0}>
            <Button type="link" size="small" onClick={() => { setDetail(r); setAiTip(null) }}>详情</Button>
            {r.status === '待审核' && (
              <>
                <Button type="link" size="small" style={{ color: '#722ed1' }}
                        icon={<RobotOutlined />} loading={aiLoading}
                        onClick={() => { setDetail(r); askAI(r) }}>
                  AI 建议
                </Button>
                <Button type="link" size="small" style={{ color: '#3f8600' }}
                        icon={<CheckOutlined />} onClick={() => submit(r, '通过', '材料齐全，同意认定')}>
                  通过
                </Button>
                <Button type="link" size="small" danger icon={<CloseOutlined />}
                        onClick={() => { setRejecting(r); setReason('') }}>
                  驳回
                </Button>
              </>
            )}
            {r.status !== '待审核' && (
              <Button type="link" size="small" onClick={() => { setDetail(r); setAiTip(null) }}>
                审核{r.status}
              </Button>
            )}
          </Space>
        ) },
    ]
  }, [entity, aiLoading]) // eslint-disable-line react-hooks/exhaustive-deps

  if (!loaded || !entity) return null

  return (
    <Card
      title="审核中心"
      extra={
        <Space>
          <Segmented
            value={group}
            options={groups.map((g) => ({ value: g, label: GROUP_LABEL[g] }))}
            onChange={(g) => {
              setGroup(g as string)
              const first = entities.find((e) => e.group === g)
              if (first) { setActiveKey(first.key); setPage(1) }
            }}
          />
          <Select
            value={activeKey} style={{ width: 190 }}
            options={groupEntities.map((e) => ({ value: e.key, label: e.label }))}
            onChange={(k) => { setActiveKey(k); setPage(1) }}
          />
          <Select value={status} style={{ width: 110 }}
                  options={['待审核', '通过', '驳回', '全部'].map((s) => ({ value: s, label: s }))}
                  onChange={(s) => { setStatus(s); setPage(1) }} />
          <Input.Search
            placeholder="学生姓名 / 学号" allowClear style={{ width: 180 }}
            onSearch={(kw) => { setKeyword(kw); setPage(1); loadRows(1, pageSize) }}
          />
          <Button icon={<RedoOutlined />} onClick={() => loadRows()} />
        </Space>
      }
    >
      <Table
        rowKey="id"
        loading={loading}
        columns={columns as never}
        dataSource={rows}
        scroll={{ x: 1100 }}
        pagination={{
          current: page, pageSize, total, showSizeChanger: true,
          showTotal: (t) => `共 ${t} 条`,
          onChange: (p, ps) => { setPage(p); setPageSize(ps); loadRows(p, ps) },
        }}
      />

      {/* 详情 + AI 建议 */}
      <Modal
        title={`${entity.label}审核详情`}
        open={!!detail}
        onCancel={() => setDetail(null)}
        width={720}
        footer={detail && detail.status === '待审核' ? (
          <Space>
            <Button icon={<RobotOutlined />} loading={aiLoading}
                    onClick={() => detail && askAI(detail)}>AI 审核建议</Button>
            <Button danger onClick={() => { setRejecting(detail); setDetail(null) }}>驳回</Button>
            <Button type="primary" style={{ background: '#3f8600' }}
                    onClick={() => detail && submit(detail, '通过', '材料齐全，同意认定')}>
              通过
            </Button>
          </Space>
        ) : null}
      >
        {detail && (
          <>
            {aiTip && (
              <Card size="small" style={{ marginBottom: 12, background: '#f6f2ff', borderColor: '#d3adf7' }}>
                <Tag color="purple">AI 建议：{aiTip.suggestion}</Tag>
                <span style={{ fontSize: 13 }}>{aiTip.reason}</span>
              </Card>
            )}
            <Space direction="vertical" size={4} style={{ width: '100%', marginBottom: 12 }}>
              <span>学生：{detail.student.name}（{detail.student.uid}，{detail.student.classId}）</span>
              {entity.fields.map((f) => {
                const v = (detail as unknown as Record<string, unknown>)[f.name]
                return v
                  ? <span key={f.name}>{f.label}：<b>{String(v).replace('·', ' / ')}</b></span>
                  : null
              })}
              <span>提交时间：{detail.createdAt}　状态：<Tag color={STATUS_COLOR[detail.status]}>{detail.status}</Tag></span>
              {detail.status !== '待审核' && (
                <span>审核人：{detail.auditor}　审核时间：{detail.auditTime}　意见：{detail.opinion}</span>
              )}
            </Space>
            <Image.PreviewGroup>
              <Space wrap>
                {detail.files?.length
                  ? detail.files.map((f) => (
                    <Image key={f.url} src={f.url} width={110} height={110}
                           style={{ objectFit: 'cover', borderRadius: 6 }} />
                  ))
                  : <span style={{ color: '#999' }}>未上传佐证材料</span>}
              </Space>
            </Image.PreviewGroup>
          </>
        )}
      </Modal>

      {/* 驳回原因 */}
      <Modal
        title="驳回申请"
        open={!!rejecting}
        onCancel={() => setRejecting(null)}
        onOk={async () => {
          if (rejecting) await submit(rejecting, '驳回', reason || '材料不符合要求')
        }}
        okText="确认驳回"
        okButtonProps={{ danger: true }}
      >
        <Input.TextArea
          rows={3} value={reason} onChange={(e) => setReason(e.target.value)}
          placeholder="请填写驳回原因（学生可见，将根据原因修改后重新提交）"
        />
      </Modal>
    </Card>
  )
}
