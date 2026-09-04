import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  App, Button, Card, Col, Descriptions, Form, Input, InputNumber, Modal,
  Popconfirm, Select, Space, Table, Tabs, Tag, Typography,
} from 'antd'
import {
  DeleteOutlined, EditOutlined, FormOutlined, PlusOutlined, ReloadOutlined,
} from '@ant-design/icons'
import { userAPI } from '@/api/modules'
import { useMetaStore } from '@/store/meta'
import type { GpaRow } from '@/types'

const { Text } = Typography

interface StudentRow {
  id: string; uid: string; name: string; sex?: string; classId?: string
  periods?: string; college?: string; major?: string; phone?: string
  email?: string; politicsStatus?: string
  innCredit: number; praCredit: number; sumCredit: number
}

const emptyStudent = {
  uid: '', name: '', password: '123456', sex: '男', nation: '汉族',
  politicsStatus: '共青团员', classId: '', periods: '', college: '', major: '',
  phone: '', email: '', origin: '', address: '',
}

/** 学生管理：信息维护 + 批量导入 + 综合成绩录入 */
export default function StudentManage() {
  const { message } = App.useApp()
  const { meta, loaded, load } = useMetaStore()

  const [rows, setRows] = useState<StudentRow[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(10)
  const [keyword, setKeyword] = useState('')
  const [periods, setPeriods] = useState('')
  const [loading, setLoading] = useState(false)

  const [addOpen, setAddOpen] = useState(false)
  const [batchOpen, setBatchOpen] = useState(false)
  const [batchText, setBatchText] = useState('')
  const [editing, setEditing] = useState<StudentRow | null>(null)
  const [form] = Form.useForm()

  // 综合成绩 tab
  const [gpaSid, setGpaSid] = useState<StudentRow | null>(null)
  const [gpaRows, setGpaRows] = useState<GpaRow[]>([])
  const [gpaForm] = Form.useForm()

  useEffect(() => {
    if (!loaded) load().catch(() => undefined)
  }, [loaded, load])

  const loadRows = useCallback(async (p = page, ps = pageSize, kw = keyword, pd = periods) => {
    setLoading(true)
    try {
      const data = await userAPI.students({ page: p, pageSize: ps, keyword: kw, periods: pd })
      setRows(data.list as StudentRow[])
      setTotal(data.total)
    } finally {
      setLoading(false)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page, pageSize, keyword, periods])

  useEffect(() => { loaded && loadRows() }, [loaded, page, pageSize]) // eslint-disable-line

  const loadGpa = useCallback(async (sid: string) => {
    setGpaRows(await userAPI.gpaList(sid).catch(() => []))
  }, [])
  useEffect(() => { gpaSid && loadGpa(gpaSid.id) }, [gpaSid, loadGpa])

  const submitStudent = async () => {
    const values = await form.validateFields()
    if (editing) {
      const { password, uid, ...rest } = values
      await userAPI.updateStudent(editing.id, rest)
      message.success('修改成功')
    } else {
      const { created, skipped } = await userAPI.addStudents(values)
      message.success(created.length ? `新增成功：${created.join('、')}` : '未新增')
      if (skipped.length) message.warning(`学号已存在：${skipped.join('、')}`)
    }
    setAddOpen(false)
    setEditing(null)
    loadRows()
  }

  const importBatch = async () => {
    // 批量导入格式：学号,姓名,性别,班级,学院,专业（每行一条，中文或英文逗号均可）
    const items = batchText.trim().split('\n').filter(Boolean).map((line) => {
      const [uid, name, sex, classId, college, major] = line.split(/[,，]/).map((s) => s.trim())
      return { ...emptyStudent, uid, name, sex: sex || '男', classId, college, major, periods: periods || undefined }
    }).filter((s) => s.uid && s.name)
    if (!items.length) return message.warning('未解析到有效数据')
    const { created, skipped } = await userAPI.addStudents(items)
    message.success(`导入完成：新增 ${created.length} 人${skipped.length ? `，跳过 ${skipped.length} 人` : ''}`)
    setBatchOpen(false)
    setBatchText('')
    loadRows(1)
  }

  const removeStudent = async (id: string) => {
    await userAPI.removeStudent(id)
    message.success('已删除')
    loadRows()
  }

  const columns = useMemo(() => [
    { title: '学号', dataIndex: 'uid', width: 100 },
    { title: '姓名', dataIndex: 'name', width: 90 },
    { title: '性别', dataIndex: 'sex', width: 60 },
    { title: '班级', dataIndex: 'classId', width: 110 },
    { title: '年级', dataIndex: 'periods', width: 90 },
    { title: '学院', dataIndex: 'college', ellipsis: true },
    { title: '专业', dataIndex: 'major', ellipsis: true },
    { title: '双创学分', dataIndex: 'innCredit', width: 90 },
    { title: '实践学分', dataIndex: 'praCredit', width: 90 },
    { title: '总学分', dataIndex: 'sumCredit', width: 80,
      render: (v: number) => <Tag color={v >= 6 ? 'green' : 'orange'}>{v}</Tag> },
    { title: '操作', key: 'op', width: 150,
      render: (_: unknown, r: StudentRow) => (
        <Space size={0}>
          <Button type="link" size="small" icon={<FormOutlined />}
                  onClick={() => { setGpaSid(r); gpaForm.resetFields() }}>
            成绩
          </Button>
          <Button type="link" size="small" icon={<EditOutlined />}
                  onClick={() => { setEditing(r); form.setFieldsValue(r) }}>
            编辑
          </Button>
          <Popconfirm title="删除学生及其全部记录？" onConfirm={() => removeStudent(r.id)}>
            <Button type="link" size="small" danger icon={<DeleteOutlined />}>删除</Button>
          </Popconfirm>
        </Space>
      ) },
  ], [gpaForm, form]) // eslint-disable-line react-hooks/exhaustive-deps

  const studentForm = (
    <Form form={form} layout="vertical" initialValues={emptyStudent}>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', columnGap: 12 }}>
        <Form.Item name="uid" label="学号" rules={[{ required: true }]}>
          <Input disabled={!!editing} />
        </Form.Item>
        <Form.Item name="name" label="姓名" rules={[{ required: true }]}><Input /></Form.Item>
        <Form.Item name="password" label="初始密码" hidden={!!editing} rules={[{ required: !editing }]}>
          <Input />
        </Form.Item>
        <Form.Item name="sex" label="性别">
          <Select options={[{ value: '男' }, { value: '女' }]} />
        </Form.Item>
        <Form.Item name="nation" label="民族"><Input /></Form.Item>
        <Form.Item name="politicsStatus" label="政治面貌">
          <Select options={(meta?.politics_status ?? []).map((s) => ({ value: s }))} />
        </Form.Item>
        <Form.Item name="classId" label="班级"><Input placeholder="如 202301班" /></Form.Item>
        <Form.Item name="periods" label="年级">
          <Select allowClear options={(meta?.periods ?? []).map((s) => ({ value: s }))} />
        </Form.Item>
        <Form.Item name="phone" label="手机号"><Input /></Form.Item>
        <Form.Item name="college" label="学院">
          <Select
            allowClear showSearch
            options={Object.keys(meta?.college_major ?? {}).map((s) => ({ value: s }))}
            onChange={(c) => form.setFieldValue('major', undefined)}
          />
        </Form.Item>
        <Form.Item name="major" label="专业">
          <Select
            allowClear showSearch
            options={(meta?.college_major?.[Form.useWatch('college', form) as string] ?? [])
              .map((s: string) => ({ value: s }))}
          />
        </Form.Item>
        <Form.Item name="email" label="邮箱"><Input /></Form.Item>
        <Form.Item name="origin" label="生源地"><Input /></Form.Item>
        <Form.Item name="address" label="家庭住址" style={{ gridColumn: 'span 2' }}><Input /></Form.Item>
      </div>
    </Form>
  )

  return (
    <Card
      title="学生管理"
      extra={
        <Space>
          <Select allowClear placeholder="年级" style={{ width: 110 }}
                  options={(meta?.periods ?? []).map((s) => ({ value: s }))}
                  onChange={(v) => { setPeriods(v ?? ''); setPage(1); loadRows(1, pageSize, keyword, v ?? '') }} />
          <Input.Search
            placeholder="姓名 / 学号 / 班级" allowClear style={{ width: 200 }}
            onSearch={(kw) => { setKeyword(kw); setPage(1); loadRows(1, pageSize, kw) }}
          />
          <Button icon={<ReloadOutlined />} onClick={() => loadRows()} />
          <Button icon={<PlusOutlined />} type="primary"
                  onClick={() => { setEditing(null); form.resetFields(); setAddOpen(true) }}>
            新增学生
          </Button>
          <Button onClick={() => setBatchOpen(true)}>批量导入</Button>
        </Space>
      }
    >
      <Table
        rowKey="id" loading={loading} size="small"
        columns={columns as never} dataSource={rows}
        pagination={{
          current: page, pageSize, total, showSizeChanger: true,
          showTotal: (t) => `共 ${t} 名学生`,
          onChange: (p, ps) => { setPage(p); setPageSize(ps); loadRows(p, ps) },
        }}
      />

      <Modal
        title={editing ? `编辑学生：${editing.name}` : '新增学生'}
        open={addOpen} onCancel={() => setAddOpen(false)} onOk={submitStudent}
        width={760} destroyOnClose okText={editing ? '保存' : '新增'}
      >
        {studentForm}
      </Modal>

      <Modal
        title="批量导入学生"
        open={batchOpen} onCancel={() => setBatchOpen(false)} onOk={importBatch}
        width={560} okText="解析并导入"
      >
        <Text type="secondary" style={{ fontSize: 12 }}>
          每行一条：学号,姓名,性别,班级,学院,专业（逗号分隔，默认密码 123456）
        </Text>
        <Input.TextArea
          rows={8} value={batchText} onChange={(e) => setBatchText(e.target.value)}
          placeholder={'20239001,张三,男,202301班,计算机科学与技术学院,计算机科学与技术\n20239002,李四,女,202301班,计算机科学与技术学院,软件工程'}
          style={{ marginTop: 8 }}
        />
      </Modal>

      {/* 综合成绩 */}
      <Modal
        title={`综合素质成绩：${gpaSid?.name ?? ''}（${gpaSid?.uid ?? ''}）`}
        open={!!gpaSid} onCancel={() => setGpaSid(null)} footer={null} width={860}
      >
        {gpaSid && (
          <>
            <Descriptions size="small" column={4} style={{ marginBottom: 12 }}>
              <Descriptions.Item label="学院">{gpaSid.college}</Descriptions.Item>
              <Descriptions.Item label="专业">{gpaSid.major}</Descriptions.Item>
              <Descriptions.Item label="班级">{gpaSid.classId}</Descriptions.Item>
              <Descriptions.Item label="政治面貌">{gpaSid.politicsStatus}</Descriptions.Item>
            </Descriptions>
            <Form
              form={gpaForm} layout="inline" style={{ marginBottom: 12 }}
              onFinish={async (v) => {
                await userAPI.addGpa({ sid: gpaSid.id, college: gpaSid.college, major: gpaSid.major, ...v })
                message.success('已录入')
                gpaForm.resetFields()
                loadGpa(gpaSid.id)
              }}
            >
              <Form.Item name="semester" rules={[{ required: true }]}>
                <Input placeholder="学期 如 2024-2025-1" style={{ width: 150 }} />
              </Form.Item>
              <Form.Item name="mutual" rules={[{ required: true }]}>
                <InputNumber placeholder="互评成绩" style={{ width: 100 }} />
              </Form.Item>
              <Form.Item name="comp" rules={[{ required: true }]}>
                <InputNumber placeholder="综测成绩" style={{ width: 100 }} />
              </Form.Item>
              <Form.Item name="gpa" rules={[{ required: true }]}>
                <InputNumber placeholder="GPA" step={0.01} style={{ width: 90 }} />
              </Form.Item>
              <Form.Item name="gpaRank" rules={[{ required: true }]}>
                <InputNumber placeholder="GPA排名" style={{ width: 100 }} />
              </Form.Item>
              <Form.Item name="compRank" rules={[{ required: true }]}>
                <InputNumber placeholder="综测排名" style={{ width: 100 }} />
              </Form.Item>
              <Form.Item name="maxRank" rules={[{ required: true }]}>
                <InputNumber placeholder="专业人数" style={{ width: 100 }} />
              </Form.Item>
              <Button type="primary" htmlType="submit">录入</Button>
            </Form>
            <Table
              rowKey="id" size="small" pagination={false} dataSource={gpaRows}
              columns={[
                { title: '学期', dataIndex: 'semester' },
                { title: '互评', dataIndex: 'mutual' },
                { title: '综测', dataIndex: 'comp' },
                { title: 'GPA', dataIndex: 'gpa' },
                { title: 'GPA排名', dataIndex: 'gpaRank',
                  render: (v, r: GpaRow) => `${v} / ${r.maxRank}` },
                { title: '综测排名', dataIndex: 'compRank' },
                { title: '', key: 'op', width: 70,
                  render: (_, r: GpaRow) => (
                    <Popconfirm title="删除该条成绩？" onConfirm={async () => {
                      await userAPI.removeGpa(r.id)
                      loadGpa(gpaSid.id)
                    }}>
                      <Button type="link" size="small" danger>删除</Button>
                    </Popconfirm>
                  ) },
              ]}
            />
          </>
        )}
      </Modal>
    </Card>
  )
}
