import { useCallback, useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import {
  App, Button, Card, Image, Input, Modal, Radio, Segmented, Select, Space, Table, Tag,
} from 'antd'
import { CheckOutlined, CloseOutlined, RedoOutlined, RobotOutlined, UploadOutlined } from '@ant-design/icons'
import { aiAPI, auditAPI, entityAPI } from '@/api/modules'
import { computeCredit } from '@/components/entity/fields'
import { entityImportColumns } from '@/components/entity/importColumns'
import ExcelImportModal from '@/components/common/ExcelImportModal'
import RecordLogs from '@/components/entity/RecordLogs'
import { useAuthStore } from '@/store/auth'
import { useMetaStore } from '@/store/meta'
import type { EntityMeta, EntityRecord } from '@/types'

const STATUS_COLOR: Record<string, string> = {
  待审核: 'gold', 待院长审批: 'orange', 公示中: 'blue', 通过: 'green', 驳回: 'red',
}
const GROUP_LABEL: Record<string, string> = { inn: '创新创业', practice: '社会实践', other: '荣誉与其他' }

type AuditRow = EntityRecord & {
  student: { uid: string; name: string; classId?: string; college?: string }
}

/** 审核中心：注册表驱动的统一审核界面（AI 建议 + 通过/驳回 + 院长终审/批量确认）
 *  状态机：待审核 →(辅导员通过·院长终审类)→ 待院长审批 →(院长通过)→ 公示中 →(期满)→ 通过
 *          待审核 →(辅导员通过·日常类)→ 公示中；公示中/已生效仅院长可纠错驳回 */
export default function AuditCenter() {
  const { message, modal } = App.useApp()
  const [params, setSearchParams] = useSearchParams()
  const { user } = useAuthStore()
  const isDean = user?.role === 'Dean'
  const { entities, entityByKey, meta, loaded, load } = useMetaStore()

  const groups = useMemo(() => ['inn', 'practice', 'other'] as const, [])
  const [group, setGroup] = useState<string>(
    () => entityByKey(params.get('key') ?? '')?.group ?? 'inn')
  const [activeKey, setActiveKey] = useState<string>(
    () => params.get('key') ?? entities.find((e) => e.group === 'inn')?.key ?? 'inn_chair')

  const [rows, setRows] = useState<AuditRow[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(10)
  const [status, setStatus] = useState(() =>
    useAuthStore.getState().user?.role === 'Dean' ? '待院长审批' : '待审核')
  const [keyword, setKeyword] = useState('')
  const [loading, setLoading] = useState(false)
  const [selected, setSelected] = useState<string[]>([])
  const [detail, setDetail] = useState<AuditRow | null>(null)
  const [rejecting, setRejecting] = useState<AuditRow | null>(null)
  const [reason, setReason] = useState('')
  const [aiTip, setAiTip] = useState<{ suggestion: string; reason: string } | null>(null)
  const [aiLoading, setAiLoading] = useState(false)
  const [importOpen, setImportOpen] = useState(false)
  const [importStatus, setImportStatus] = useState<'待审核' | '通过'>('待审核')

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

  // 通知深链：/audit?key=xxx&rid=yyy → 自动打开对应记录详情弹窗
  const rid = params.get('rid')
  useEffect(() => {
    if (!rid || loading || !rows.length) return
    const r = rows.find((x) => x.id === rid)
    if (r) { setDetail(r); setAiTip(null) }
    setSearchParams({}, { replace: true })
  }, [rid, rows, loading, setSearchParams])

  useEffect(() => { setSelected([]) }, [activeKey, status])

  const submit = async (r: AuditRow, result: '通过' | '驳回', opinion: string) => {
    const res = await auditAPI.submit(activeKey, r.id, result, opinion)
    message.success(
      res.status === '待院长审批' ? '初审通过，已转院长审批'
        : res.status === '公示中' ? '已通过终审，进入公示期'
          : result === '驳回' ? '已驳回，已通知学生' : '已通过')
    setDetail(null)
    setRejecting(null)
    loadRows()
  }

  /** 院长批量确认：待院长审批 → 公示期（逐条核定学分/留痕/通知） */
  const batchConfirm = () => {
    if (!selected.length) return
    const n = selected.length
    modal.confirm({
      title: `批量确认 ${n} 条申请？`,
      content: '确认后通过院长终审并进入公示期，系统将逐条核定学分、留痕并通知学生。',
      okText: '确认',
      onOk: async () => {
        const r = await auditAPI.batchConfirm(activeKey, selected)
        message.success(`已批量确认 ${r.confirmed} 条${r.skipped ? `，跳过 ${r.skipped} 条` : ''}`)
        setSelected([])
        loadRows()
      },
    })
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

  /** 补录导入模板列：学号必填（指定归属学生），其余列与实体表单同源动态生成 */
  const importCols = useMemo(() => [
    { key: 'sid', title: '学号', required: true, example: '记录归属学生的学号，须为本院系学生' },
    ...entityImportColumns(entity, meta),
  ], [entity, meta]) // eslint-disable-line react-hooks/exhaustive-deps

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
      { title: '状态', dataIndex: 'status', width: 96,
        render: (s: string) => <Tag color={STATUS_COLOR[s]}>{s}</Tag> },
      { title: '操作', key: 'op', width: isDean ? 250 : 210, fixed: 'right' as const,
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
                  {entity?.deanReview ? '初审通过' : '通过'}
                </Button>
                <Button type="link" size="small" danger icon={<CloseOutlined />}
                        onClick={() => { setRejecting(r); setReason('') }}>
                  驳回
                </Button>
              </>
            )}
            {r.status === '待院长审批' && isDean && (
              <>
                <Button type="link" size="small" style={{ color: '#3f8600' }} icon={<CheckOutlined />}
                        onClick={() => submit(r, '通过', '终审通过，同意认定')}>
                  终审通过
                </Button>
                <Button type="link" size="small" danger icon={<CloseOutlined />}
                        onClick={() => { setRejecting(r); setReason('') }}>
                  驳回
                </Button>
              </>
            )}
            {r.status === '公示中' && isDean && (
              <Button type="link" size="small" danger icon={<CloseOutlined />}
                      onClick={() => { setRejecting(r); setReason('') }}>
                公示异议驳回
              </Button>
            )}
            {r.status === '通过' && isDean && (
              <Button type="link" size="small" danger icon={<CloseOutlined />}
                      onClick={() => { setRejecting(r); setReason('') }}>
                纠错驳回
              </Button>
            )}
            {r.status !== '待审核' && !isDean && r.status !== '待院长审批' && (
              <Button type="link" size="small" onClick={() => { setDetail(r); setAiTip(null) }}>
                审核{r.status}
              </Button>
            )}
          </Space>
        ) },
    ]
  }, [entity, aiLoading, isDean]) // eslint-disable-line react-hooks/exhaustive-deps

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
          <Select value={status} style={{ width: 124 }}
                  options={['待审核', '待院长审批', '公示中', '通过', '驳回', '全部'].map((s) => ({ value: s, label: s }))}
                  onChange={(s) => { setStatus(s); setPage(1) }} />
          <Input.Search
            placeholder="学生姓名 / 学号" allowClear style={{ width: 180 }}
            onSearch={(kw) => { setKeyword(kw); setPage(1); loadRows(1, pageSize) }}
          />
          <Button icon={<UploadOutlined />} onClick={() => setImportOpen(true)}>Excel 导入</Button>
          <Button icon={<RedoOutlined />} onClick={() => loadRows()} />
        </Space>
      }
    >
      {isDean && status === '待院长审批' && (
        <Space style={{ marginBottom: 12 }}>
          <Button type="primary" disabled={!selected.length} icon={<CheckOutlined />} onClick={batchConfirm}>
            批量确认{selected.length ? `（${selected.length}）` : ''}
          </Button>
          {selected.length > 0 && (
            <span style={{ color: '#999', fontSize: 13 }}>
              已勾选 {selected.length} 条，确认后通过终审并进入公示期
            </span>
          )}
        </Space>
      )}
      <Table
        rowKey="id"
        loading={loading}
        columns={columns as never}
        dataSource={rows}
        scroll={{ x: 1100 }}
        rowSelection={isDean && status === '待院长审批' ? {
          selectedRowKeys: selected,
          onChange: (keys) => setSelected(keys as string[]),
        } : undefined}
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
        footer={detail && (
          detail.status === '待审核' || (detail.status === '待院长审批' && isDean) ||
          ((detail.status === '公示中' || detail.status === '通过') && isDean)
        ) ? (
          <Space>
            {detail.status === '待审核' && (
              <>
                <Button icon={<RobotOutlined />} loading={aiLoading}
                        onClick={() => detail && askAI(detail)}>AI 审核建议</Button>
                <Button danger onClick={() => { setRejecting(detail); setDetail(null) }}>驳回</Button>
                <Button type="primary" style={{ background: '#3f8600' }}
                        onClick={() => detail && submit(detail, '通过', '材料齐全，同意认定')}>
                  {entity.deanReview ? '初审通过' : '通过'}
                </Button>
              </>
            )}
            {detail.status === '待院长审批' && isDean && (
              <>
                <Button danger onClick={() => { setRejecting(detail); setDetail(null) }}>驳回</Button>
                <Button type="primary" style={{ background: '#3f8600' }}
                        onClick={() => detail && submit(detail, '通过', '终审通过，同意认定')}>
                  终审通过
                </Button>
              </>
            )}
            {detail.status === '公示中' && isDean && (
              <Button danger onClick={() => { setRejecting(detail); setDetail(null) }}>公示异议驳回</Button>
            )}
            {detail.status === '通过' && isDean && (
              <Button danger onClick={() => { setRejecting(detail); setDetail(null) }}>纠错驳回</Button>
            )}
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
              {(() => {
                if (!meta) return null
                const kvField = entity.fields.find((f) => f.type === 'kv')
                const kvValue = kvField
                  ? (detail as unknown as Record<string, unknown>)[kvField.name] as string : undefined
                const post = (detail as unknown as Record<string, unknown>).post as string | undefined
                const ass = computeCredit(meta, kvField?.kvCategory, kvValue, post)
                return ass
                  ? <span style={{ color: '#d46b08', fontWeight: 600 }}>
                      规则核定学分：
                      {ass.factor !== 1
                        ? `${ass.base} × ${ass.factor}（${post}）= `
                        : ''}
                      {ass.credit} 学分{detail.status === '待审核' ? '（通过后按此核定）' : ''}
                    </span>
                  : null
              })()}
              <span>提交时间：{detail.createdAt}　状态：<Tag color={STATUS_COLOR[detail.status]}>{detail.status}</Tag></span>
              {detail.status === '待院长审批' && (
                <span style={{ color: '#d46b08' }}>辅导员已初审通过，等待院长终审</span>
              )}
              {detail.status === '公示中' && detail.publicEnd && (
                <span style={{ color: '#1677ff' }}>
                  公示期至：<b>{detail.publicEnd}</b>（期满自动生效，学分届时计入）
                </span>
              )}
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
            <RecordLogs entityKey={activeKey} recordId={detail.id} />
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

      {/* Excel 批量导入（补录历史数据）：学号指定归属学生，可直接置为通过并核定学分 */}
      <ExcelImportModal
        open={importOpen}
        title={`批量导入${entity.label}`}
        columns={importCols}
        extra={
          <Space>
            <span style={{ fontSize: 13 }}>导入状态：</span>
            <Radio.Group
              value={importStatus}
              onChange={(e) => setImportStatus(e.target.value as '待审核' | '通过')}
              optionType="button"
              options={[
                { value: '待审核', label: '待审核（走审核流程）' },
                { value: '通过', label: '直接通过（历史数据补录）' },
              ]}
            />
          </Space>
        }
        doImport={(rows) => entityAPI.importEntities(activeKey, { rows, status: importStatus })}
        onDone={() => { setPage(1); loadRows(1, pageSize) }}
        onClose={() => setImportOpen(false)}
      />
    </Card>
  )
}
