import { useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { App, Button, Card, Form, Input, Tag, Typography } from 'antd'
import { KeyOutlined, UserOutlined } from '@ant-design/icons'
import { authAPI } from '@/api/modules'
import { useAuthStore } from '@/store/auth'

const { Text } = Typography

export default function Login() {
  const { message } = App.useApp()
  const navigate = useNavigate()
  const location = useLocation()
  const { setAuth } = useAuthStore()
  const [loading, setLoading] = useState(false)

  const onFinish = async (values: { uid: string; password: string }) => {
    setLoading(true)
    try {
      const { token, user } = await authAPI.login(values.uid, values.password)
      setAuth(token, user)
      message.success(`欢迎回来，${user.name}${user.role === 'Student' ? '同学' : '老师'}`)
      navigate((location.state as { from?: string })?.from ?? '/dashboard', { replace: true })
    } catch {
      /* 拦截器已提示 */
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="login-page">
      <Card className="login-card" styles={{ body: { padding: 0 } }}>
        <div className="login-title">AI 学生成长发展系统</div>
        <div className="login-sub">Student Growth &amp; Development System</div>
        <Form layout="vertical" onFinish={onFinish} initialValues={{ uid: '', password: '' }}>
          <Form.Item name="uid" rules={[{ required: true, message: '请输入学号/工号' }]}>
            <Input size="large" prefix={<UserOutlined />} placeholder="学号 / 工号" />
          </Form.Item>
          <Form.Item name="password" rules={[{ required: true, message: '请输入密码' }]}>
            <Input.Password size="large" prefix={<KeyOutlined />} placeholder="密码" />
          </Form.Item>
          <Button type="primary" size="large" htmlType="submit" block loading={loading}>
            登 录
          </Button>
        </Form>
        <div style={{ marginTop: 20, display: 'grid', gap: 4 }}>
          <Text type="secondary" style={{ fontSize: 12 }}>演示账号（密码均为 123456）：</Text>
          <Text style={{ fontSize: 12 }}><Tag color="blue">学生</Tag>202300001 ~ 202300012</Text>
          <Text style={{ fontSize: 12 }}><Tag color="green">辅导员</Tag>C0001</Text>
          <Text style={{ fontSize: 12 }}><Tag color="purple">院长</Tag>D0001</Text>
        </div>
      </Card>
    </div>
  )
}
