import { useEffect, useState } from 'react'
import {
  App, Avatar, Button, Card, Col, Form, Input, Modal, Row,
  Select, Upload,
} from 'antd'
import { KeyOutlined, UploadOutlined, UserOutlined } from '@ant-design/icons'
import { authAPI, filesAPI } from '@/api/modules'
import { useAuthStore } from '@/store/auth'
import { useMetaStore } from '@/store/meta'
import type { Role } from '@/types'

export default function InfoPage() {
  const { message } = App.useApp()
  const { user, setUser } = useAuthStore()
  const { meta, loaded, load } = useMetaStore()
  const [form] = Form.useForm()
  const [pwdOpen, setPwdOpen] = useState(false)
  const [pwdForm] = Form.useForm()
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (!loaded) load().catch(() => undefined)
  }, [loaded, load])

  useEffect(() => {
    if (user) form.setFieldsValue(user)
  }, [user, form])

  if (!user) return null
  const roleLabel: Record<Role, string> = { Student: '学生', Counsellor: '辅导员', Dean: '院长' }

  const save = async () => {
    const values = await form.validateFields()
    setSaving(true)
    try {
      const updated = await authAPI.updateMe(values)
      setUser({ ...user, ...updated })
      message.success('保存成功')
    } finally {
      setSaving(false)
    }
  }

  const uploadPhoto = async (file: File) => {
    const [f] = await filesAPI.upload([file])
    const updated = await authAPI.updateMe({ photo: f.url })
    setUser({ ...user, ...updated })
    message.success('头像已更新')
  }

  const changePwd = async () => {
    const { oldPassword, newPassword } = await pwdForm.validateFields()
    await authAPI.changePassword(oldPassword, newPassword)
    message.success('密码修改成功，请牢记新密码')
    setPwdOpen(false)
    pwdForm.resetFields()
  }

  return (
    <Row gutter={16}>
      <Col span={7}>
        <Card style={{ textAlign: 'center' }}>
          <Avatar size={110} icon={<UserOutlined />} src={user.photo} style={{ marginBottom: 12 }} />
          <div style={{ fontSize: 17, fontWeight: 600 }}>{user.name}</div>
          <div style={{ color: '#999' }}>{roleLabel[user.role]} · {user.uid}</div>
          {user.role === 'Student' && user.counsellorName && (
            <div style={{ color: '#999', fontSize: 12, marginTop: 4 }}>辅导员：{user.counsellorName}</div>
          )}
          <div style={{ marginTop: 16, display: 'grid', gap: 8 }}>
            <Upload
              accept=".jpg,.jpeg,.png" showUploadList={false}
              customRequest={({ file }) => uploadPhoto(file as File)}
            >
              <Button icon={<UploadOutlined />} block>更换头像</Button>
            </Upload>
            <Button icon={<KeyOutlined />} block onClick={() => setPwdOpen(true)}>修改密码</Button>
          </div>
        </Card>
      </Col>
      <Col span={17}>
        <Card title="基本信息" extra={<Button type="primary" loading={saving} onClick={save}>保存</Button>}>
          <Form form={form} layout="vertical">
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', columnGap: 16 }}>
              <Form.Item name="name" label="姓名" rules={[{ required: true }]}><Input /></Form.Item>
              {user.role === 'Student' && (
                <>
                  <Form.Item name="sex" label="性别">
                    <Select options={[{ value: '男' }, { value: '女' }]} />
                  </Form.Item>
                  <Form.Item name="nation" label="民族"><Input /></Form.Item>
                  <Form.Item name="politicsStatus" label="政治面貌">
                    <Select options={(meta?.politics_status ?? []).map((s) => ({ value: s }))} />
                  </Form.Item>
                  <Form.Item name="classId" label="班级"><Input disabled /></Form.Item>
                  <Form.Item name="periods" label="年级"><Input disabled /></Form.Item>
                  <Form.Item name="college" label="学院"><Input disabled /></Form.Item>
                  <Form.Item name="major" label="专业"><Input disabled /></Form.Item>
                  <Form.Item name="origin" label="生源地"><Input /></Form.Item>
                  <Form.Item name="address" label="家庭住址"><Input /></Form.Item>
                </>
              )}
              {user.role !== 'Student' && (
                <Form.Item name="title" label="职务"><Input /></Form.Item>
              )}
              <Form.Item name="phone" label="手机号"><Input /></Form.Item>
              <Form.Item name="email" label="邮箱"><Input /></Form.Item>
            </div>
          </Form>
        </Card>
      </Col>

      <Modal
        title="修改密码" open={pwdOpen} onCancel={() => setPwdOpen(false)} onOk={changePwd} destroyOnClose
      >
        <Form form={pwdForm} layout="vertical">
          <Form.Item name="oldPassword" label="原密码" rules={[{ required: true }]}>
            <Input.Password />
          </Form.Item>
          <Form.Item name="newPassword" label="新密码（6-32位）"
                      rules={[{ required: true }, { min: 6, max: 32 }]}>
            <Input.Password />
          </Form.Item>
          <Form.Item dependencies={['newPassword']} noStyle>
            {({ getFieldValue }) => (
              <Form.Item
                name="confirm" label="确认新密码"
                rules={[
                  { required: true },
                  () => ({
                    validator: (_, v) =>
                      v === getFieldValue('newPassword')
                        ? Promise.resolve()
                        : Promise.reject(new Error('两次输入不一致')),
                  }),
                ]}
              >
                <Input.Password />
              </Form.Item>
            )}
          </Form.Item>
        </Form>
      </Modal>
    </Row>
  )
}
