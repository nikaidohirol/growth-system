import { useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { App, Button, Card, Form, Input } from 'antd'
import { KeyOutlined, UserOutlined } from '@ant-design/icons'
import { authAPI } from '@/api/modules'
import { useAuthStore } from '@/store/auth'
import collegeLogo from '@/assets/college-logo.png'

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
        <img className="login-logo" src={collegeLogo} alt="汽车工程学院" draggable={false} />
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
      </Card>
    </div>
  )
}
