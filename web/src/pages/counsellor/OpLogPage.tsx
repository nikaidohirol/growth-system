import { useEffect, useState } from 'react'
import { Card, DatePicker, Input, Select, Table, Tag, Typography } from 'antd'
import type { ColumnsType, TablePaginationConfig } from 'antd/es/table'
import { oplogAPI } from '@/api/modules'
import { useMetaStore } from '@/store/meta'
import type { OperationLog } from '@/types'

const { Title, Text } = Typography

const ACTION_META: Record<OperationLog['action'], { color: string; label: string }> = {
  create: { color: 'blue', label: '申报' },
  update: { color: 'orange', label: '修改' },
  delete: { color: 'red', label: '删除' },
  audit: { color: 'green', label: '审核' },
  login: { color: 'default', label: '登录' },
}

const ROLE_LABEL: Record<string, string> = {
  Student: '学生', Counsellor: '辅导员', Dean: '院长',
}

/** 操作日志页（辅导员/院长）— 合规留痕检索：谁、何时、对什么、做了什么 */
export default function OpLogPage() {
  const { entities, loaded, load } = useMetaStore()
  const [list, setList] = useState<OperationLog[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(15)
  const [loading, setLoading] = useState(false)
  const [action, setAction] = useState<string | undefined>()
  const [key, setKey] = useState<string | undefined>()
  const [keyword, setKeyword] = useState('')
  const [range, setRange] = useState<[string, string] | null>(null)

  useEffect(() => { if (!loaded) load().catch(() => undefined) }, [loaded, load])

  useEffect(() => {
    setLoading(true)
    const params: Record<string, unknown> = { page, pageSize }
    if (action) params.action = action
    if (key) params.key = key
    if (keyword) params.keyword = keyword
    if (range) { params.start = range[0]; params.end = range[1] }
    oplogAPI.logs(params)
      .then((d) => { setList(d.list); setTotal(d.total) })
      .catch(() => undefined)
      .finally(() => setLoading(false))
  }, [page, pageSize, action, key, keyword, range])

  const columns: ColumnsType<OperationLog> = [
    {
      title: '时间', width: 170, fixed: 'left' as const,
      dataIndex: 'createdAt',
      render: (v: string) => <Text type="secondary" style={{ fontSize: 12 }}>{v}</Text>,
    },
    {
      title: '操作人', width: 150, fixed: 'left' as const,
      render: (_, r) => (
        <>
          {r.operatorName}
          <Tag style={{ marginLeft: 8 }} color={r.role === 'Student' ? 'blue' : r.role === 'Counsellor' ? 'cyan' : 'purple'}>
            {ROLE_LABEL[r.role] ?? r.role}
          </Tag>
        </>
      ),
    },
    {
      title: '动作', width: 80,
      dataIndex: 'action',
      render: (a: OperationLog['action']) => {
        const meta = ACTION_META[a] ?? ACTION_META.update
        return <Tag color={meta.color}>{meta.label}</Tag>
      },
    },
    {
      title: '涉及板块', width: 130,
      dataIndex: 'entityLabel',
      render: (v?: string | null) => v ?? '-',
    },
    { title: '摘要', ellipsis: true, dataIndex: 'summary' },
  ]

  const onTableChange = (p: TablePaginationConfig) => {
    setPage(p.current ?? 1)
    setPageSize(p.pageSize ?? 15)
  }

  return (
    <Card style={{ minWidth: 1080 }}>
      <Title level={4} style={{ marginTop: 0 }}>操作日志</Title>
      <Text type="secondary" style={{ display: 'block', marginBottom: 16 }}>
        全量留痕、只增不删：记录每一笔申报、修改、删除、审核与登录，满足审计合规要求
      </Text>
      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginBottom: 16 }}>
        <Select
          allowClear placeholder="全部动作" style={{ width: 120 }} value={action}
          onChange={(v) => { setAction(v); setPage(1) }}
          options={Object.entries(ACTION_META).map(([k, v]) => ({ value: k, label: v.label }))}
        />
        <Select
          showSearch allowClear placeholder="全部板块" style={{ width: 180 }} value={key}
          onChange={(v) => { setKey(v); setPage(1) }}
          optionFilterProp="label"
          options={loaded ? entities.map((e) => ({ value: e.key, label: e.label })) : []}
        />
        <Input.Search
          allowClear placeholder="搜索操作人 / 摘要" style={{ width: 260 }}
          onSearch={(v) => { setKeyword(v); setPage(1) }}
        />
        <DatePicker.RangePicker
          onChange={(_, strs) => {
            setRange(strs[0] && strs[1] ? [strs[0], strs[1]] : null)
            setPage(1)
          }}
        />
      </div>
      <Table
        rowKey="id" loading={loading} columns={columns} dataSource={list}
        pagination={{ current: page, pageSize, total, showSizeChanger: true, showQuickJumper: true, showTotal: (t) => `共 ${t} 条` }}
        onChange={onTableChange}
      />
    </Card>
  )
}
