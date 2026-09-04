import { Button, Result } from 'antd'
import { useNavigate } from 'react-router-dom'

export default function NotFound() {
  const navigate = useNavigate()
  return (
    <Result
      style={{ marginTop: 60 }}
      status="404"
      title="404"
      subTitle="页面不存在或无权访问"
      extra={<Button type="primary" onClick={() => navigate('/dashboard')}>返回主面板</Button>}
    />
  )
}
