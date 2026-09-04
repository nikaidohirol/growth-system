import { useCallback, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { useLocation } from 'react-router-dom'
import {
  App, Button, Card, Descriptions, Form, Image, Input, Modal, Popconfirm,
  Select, Space, Spin, Table, Tag, Upload,
} from 'antd'
import {
  DeleteOutlined, EditOutlined, InboxOutlined, PlusOutlined, RobotOutlined,
  SearchOutlined, EyeOutlined,
} from '@ant-design/icons'
import { aiAPI, entityAPI, filesAPI } from '@/api/modules'
import { useMetaStore } from '@/store/meta'
import { formToPayload, recordToForm, renderFormField } from '@/components/entity/fields'
import type { EntityMeta, EntityRecord, FieldMeta } from '@/types'

const STATUS_COLOR: Record<string, string> = { 待审核: 'gold', 通过: 'green', 驳回: 'red' }

function statusTag(status: string) {
  return <Tag color={STATUS_COLOR[status] ?? 'default'}>{status}</Tag>
}

function renderCell(field: FieldMeta, value: unknown) {
  if (value === null || value === undefined || value === '') return '-'
  if (field.type === 'kv') return String(value).replace('·', ' / ')
  return String(value)
}

/** 泛型实体页：一份契约驱动 表格/搜索/新增(AI 填充)/编辑/详情/删除 */
export default function EntityPage() {
  const { message } = App.useApp()
  const location = useLocation()
  const key = location.pathname.split('/').pop() as string
  const { entityByKey, meta, loaded, load } = useMetaStore()
  const entity = entityByKey(key)

  const [rows, setRows] = useState<EntityRecord[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(10)
  const [keyword, setKeyword] = useState('')
  const [loading, setLoading] = useState(false)

  const [form] = Form.useForm()
  const [modalOpen, setModalOpen] = useState(false)
  const [editing, setEditing] = useState<EntityRecord | null>(null)
  const [detail, setDetail] = useState<EntityRecord | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [kv, setKv] = useState<{ chiefly?: string; minor?: string }>({})
  const [fileList, setFileList] = useState<{ label: string; url: string }[]>([])
  const [aiDesc, setAiDesc] = useState('')
  const [aiLoading, setAiLoading] = useState(false)

  useEffect(() => {
    if (!loaded) load().catch(() => undefined)
  }, [loaded, load])

  const loadRows = useCallback(async (p = page, ps = pageSize, kw = keyword) => {
    if (!entity) return
    setLoading(true)
    try {
      const data = await entityAPI.list(key, { page: p, pageSize: ps, keyword: kw })
      setRows(data.list)
      setTotal(data.total)
    } finally {
      setLoading(false)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [entity, key, page, pageSize, keyword])

  useEffect(() => {
    if (entity) loadRows()
  }, [entity, page, pageSize]) // eslint-disable-line react-hooks/exhaustive-deps

  const openCreate = () => {
    setEditing(null)
    setKv({})
    setFileList([])
    setAiDesc('')
    form.resetFields()
    setModalOpen(true)
  }

  const openEdit = (r: EntityRecord) => {
    setEditing(r)
    setFileList(r.files ?? [])
    setAiDesc('')
    form.resetFields()
    const init = recordToForm(entity as EntityMeta, r as unknown as Record<string, any>)
    if (init._kv) setKv(init._kv)
    else setKv({})
    form.setFieldsValue(init)
    setModalOpen(true)
  }

  const aiFill = async () => {
    if (!aiDesc.trim() || !entity) return
    setAiLoading(true)
    try {
      const { fields } = await aiAPI.formAssist(key, aiDesc)
      const values = form.getFieldsValue()
      for (const [name, label] of Object.entries(fields)) {
        const f = entity.fields.find((x) => x.name === name)
        if (!f || !label) continue
        if (f.type === 'kv') {
          const [chiefly, minor] = String(label).split(/[·/]/).map((s) => s.trim())
          if (chiefly && minor) setKv({ chiefly, minor })
        } else {
          values[name] = label
        }
      }
      form.setFieldsValue(values)
      message.success('AI 已根据描述填充表单，请核对后提交')
    } catch {
      /* 拦截器已提示 */
    } finally {
      setAiLoading(false)
    }
  }

  const submit = async () => {
    if (!entity) return
    const values = await form.validateFields()
    setSubmitting(true)
    try {
      const payload = formToPayload(entity, values, kv)
      payload.files = fileList
      if (editing) await entityAPI.update(key, editing.id, payload)
      else await entityAPI.create(key, payload)
      message.success(editing ? '修改成功，已重新提交审核' : '提交成功，等待审核')
      setModalOpen(false)
      loadRows(1, pageSize, keyword)
      setPage(1)
    } catch {
      /* 拦截器已提示 */
    } finally {
      setSubmitting(false)
    }
  }

  const remove = async (id: string) => {
    await entityAPI.remove(key, id)
    message.success('删除成功')
    loadRows()
  }

  const columns = useMemo(() => {
    if (!entity) return []
    const cols: {
      title: string; dataIndex?: string; key: string; ellipsis?: boolean
      width?: number; render?: (v: unknown) => ReactNode
    }[] = entity.fields.filter((f) => f.inTable).map((f) => ({
      title: f.label,
      dataIndex: f.name,
      key: f.name,
      ellipsis: true,
      render: (v: unknown) => renderCell(f, v),
    }))
    cols.push({
      title: '状态', dataIndex: 'status', key: 'status', width: 90,
      render: (v: unknown) => statusTag(String(v)),
    })
    return cols
  }, [entity])

  if (!loaded || !entity || !meta) return <Spin style={{ display: 'block', margin: '120px auto' }} />

  return (
    <Card
      title={entity.label}
      extra={
        <Space>
          <Input
            allowClear
            prefix={<SearchOutlined />}
            placeholder={`搜索${entity.searchPlaceholder}`}
            style={{ width: 220 }}
            onPressEnter={(e) => {
              const kw = (e.target as HTMLInputElement).value
              setKeyword(kw)
              setPage(1)
              loadRows(1, pageSize, kw)
            }}
          />
          <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
            新增申请
          </Button>
        </Space>
      }
    >
      <Table
        rowKey="id"
        loading={loading}
        columns={[
          ...columns,
          {
            title: '操作', key: 'action', width: 170, fixed: 'right',
            render: (_, r: EntityRecord) => (
              <Space size={0}>
                <Button type="link" size="small" icon={<EyeOutlined />}
                        onClick={() => setDetail(r)}>
                  详情
                </Button>
                {r.status !== '通过' && (
                  <Button type="link" size="small" icon={<EditOutlined />} onClick={() => openEdit(r)}>
                    {r.status === '驳回' ? '修改重报' : '编辑'}
                  </Button>
                )}
                {r.status !== '通过' && (
                  <Popconfirm title="确认删除该记录？" onConfirm={() => remove(r.id)}>
                    <Button type="link" size="small" danger icon={<DeleteOutlined />}>删除</Button>
                  </Popconfirm>
                )}
              </Space>
            ),
          },
        ]}
        dataSource={rows}
        pagination={{
          current: page, pageSize, total, showSizeChanger: true, showTotal: (t) => `共 ${t} 条`,
          onChange: (p, ps) => {
            setPage(p)
            setPageSize(ps)
            loadRows(p, ps, keyword)
          },
        }}
        expandable={{
          expandedRowRender: (r: EntityRecord) => (
            <Space size={16} wrap>
              {r.opinion && <span>审核意见：<Tag color={STATUS_COLOR[r.status]}>{r.opinion}</Tag></span>}
              {r.auditor && <span>审核人：{r.auditor}</span>}
              {r.auditTime && <span>审核时间：{r.auditTime}</span>}
              {r.files?.length
                ? r.files.map((f) => (
                  <a key={f.url} href={f.url} target="_blank" rel="noreferrer">📎 {f.label}</a>
                ))
                : <span style={{ color: '#999' }}>无佐证材料</span>}
            </Space>
          ),
        }}
      />

      {/* 新增 / 编辑 */}
      <Modal
        title={editing ? `修改${entity.label}` : `新增${entity.label}`}
        open={modalOpen}
        onCancel={() => setModalOpen(false)}
        width={680}
        destroyOnClose
        footer={[
          <Button key="cancel" onClick={() => setModalOpen(false)}>取消</Button>,
          <Button key="ok" type="primary" loading={submitting} onClick={submit}>
            {editing ? '重新提交审核' : '提交申请'}
          </Button>,
        ]}
      >
        {!editing && (
          <Card size="small" style={{ marginBottom: 16, background: '#f7f9ff' }}>
            <Space.Compact style={{ width: '100%' }}>
              <Input
                placeholder="一句话描述你的经历，AI 自动填表。如：2024年11月获全国大学生数学建模竞赛国家二等奖，第一完成人"
                value={aiDesc}
                onChange={(e) => setAiDesc(e.target.value)}
                onPressEnter={aiFill}
              />
              <Button type="primary" ghost loading={aiLoading} icon={<RobotOutlined />} onClick={aiFill}>
                AI 智能填充
              </Button>
            </Space.Compact>
          </Card>
        )}
        <Form form={form} layout="vertical">
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', columnGap: 16 }}>
            {entity.fields.map((f) => (
              <Form.Item
                key={f.name}
                name={f.name}
                label={f.label}
                rules={f.required ? [{ required: true, message: `${f.label}不能为空` }] : []}
                style={f.half ? undefined : { gridColumn: '1 / -1' }}
              >
                {renderFormField(f, meta, form, kv, setKv)}
              </Form.Item>
            ))}
            <Form.Item label="佐证材料" style={{ gridColumn: '1 / -1' }}>
              <Upload.Dragger
                multiple
                accept=".jpg,.jpeg,.png,.gif,.webp,.pdf"
                showUploadList={false}
                customRequest={async ({ file, onSuccess }) => {
                  const saved = await filesAPI.upload([file as File])
                  setFileList((prev) => [...prev, ...saved])
                  onSuccess?.(saved)
                }}
              >
                <p style={{ margin: 8 }}><InboxOutlined style={{ fontSize: 28, color: '#3b6fe0' }} /></p>
                <p style={{ fontSize: 12, color: '#999' }}>点击或拖拽上传佐证材料（jpg/png/pdf ≤10MB）</p>
              </Upload.Dragger>
              {fileList.length > 0 && (
                <Space wrap style={{ marginTop: 8 }}>
                  {fileList.map((f, i) => (
                    <Tag
                      key={f.url + i}
                      closable
                      onClose={() => setFileList((prev) => prev.filter((x) => x.url !== f.url))}
                    >
                      <a href={f.url} target="_blank" rel="noreferrer">{f.label}</a>
                    </Tag>
                  ))}
                </Space>
              )}
            </Form.Item>
          </div>
        </Form>
      </Modal>

      {/* 详情 */}
      <Modal
        title={`${entity.label}详情`}
        open={!!detail}
        onCancel={() => setDetail(null)}
        footer={null}
        width={640}
      >
        {detail && (
          <>
            <Descriptions column={2} size="small" bordered>
              {entity.fields.map((f) => (
                <Descriptions.Item key={f.name} label={f.label}>
                  {renderCell(f, (detail as unknown as Record<string, unknown>)[f.name])}
                </Descriptions.Item>
              ))}
              <Descriptions.Item label="状态">{statusTag(detail.status)}</Descriptions.Item>
              <Descriptions.Item label="审核意见">{detail.opinion || '-'}</Descriptions.Item>
              <Descriptions.Item label="审核人">{detail.auditor || '-'}</Descriptions.Item>
              <Descriptions.Item label="审核时间">{detail.auditTime || '-'}</Descriptions.Item>
            </Descriptions>
            {detail.files?.length > 0 && (
              <Space wrap style={{ marginTop: 12 }}>
                {detail.files.map((f) => (
                  <Image key={f.url} src={f.url} alt={f.label} width={96} height={96}
                         style={{ objectFit: 'cover', borderRadius: 6 }} />
                ))}
              </Space>
            )}
          </>
        )}
      </Modal>
    </Card>
  )
}
