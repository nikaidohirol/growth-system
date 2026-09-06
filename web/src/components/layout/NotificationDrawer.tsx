import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { App, Badge, Button, Drawer, Empty, List, Tag, Typography } from 'antd'
import { CheckOutlined } from '@ant-design/icons'
import { notificationAPI } from '@/api/modules'
import { useAuthStore } from '@/store/auth'
import type { NotificationItem } from '@/types'

const { Text } = Typography

/** 通知中心抽屉：未读高亮，点击标记已读并深链到对应记录详情 */
export default function NotificationDrawer({ open, unread, onClose, onChanged }: {
  open: boolean
  unread: number
  onClose: () => void
  /** 已读动作后同步 Header 铃铛徽标 */
  onChanged: (unread: number) => void
}) {
  const { message } = App.useApp()
  const navigate = useNavigate()
  const { user } = useAuthStore()
  const [list, setList] = useState<NotificationItem[]>([])
  const [page, setPage] = useState(1)
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)

  const load = useCallback(async (p = 1) => {
    setLoading(true)
    try {
      const d = await notificationAPI.list({ page: p, pageSize: 10 })
      setList(d.list)
      setTotal(d.total)
      setPage(p)
      onChanged(d.unread)
    } finally {
      setLoading(false)
    }
  }, [onChanged])

  useEffect(() => {
    if (open) load(1)
  }, [open, load])

  const markRead = async (ids: string[]) => {
    await notificationAPI.read({ ids })
    load(page)
  }

  const readAll = async () => {
    await notificationAPI.read({ all: true })
    message.success('已全部标记为已读')
    load(page)
  }

  const openItem = async (n: NotificationItem) => {
    if (!n.isRead) await markRead([n.id])
    if (n.linkKey && n.linkId) {
      // 学生去实体页直接看详情；辅导员/院长去审核中心（/entity 路由仅学生可用）
      if (user?.role === 'Student') navigate(`/entity/${n.linkKey}?rid=${n.linkId}`)
      else navigate(`/audit?key=${n.linkKey}&rid=${n.linkId}`)
    }
    onClose()
  }

  return (
    <Drawer
      open={open}
      onClose={onClose}
      width={420}
      title={<Badge count={unread} offset={[8, -2]}>通知中心</Badge>}
      extra={
        <Button size="small" icon={<CheckOutlined />} disabled={unread === 0} onClick={readAll}>
          全部已读
        </Button>
      }
      styles={{ body: { padding: '0 16px' } }}
    >
      <List
        loading={loading}
        dataSource={list}
        locale={{ emptyText: <Empty description="暂无通知" /> }}
        pagination={{
          size: 'small', current: page, total, pageSize: 10,
          onChange: (p) => load(p), hideOnSinglePage: true,
        }}
        renderItem={(n) => (
          <List.Item style={{ cursor: 'pointer', padding: '12px 4px' }} onClick={() => openItem(n)}>
            <List.Item.Meta
              title={
                <span style={{ fontWeight: n.isRead ? 400 : 600, fontSize: 14 }}>
                  {!n.isRead && <Tag color="blue" style={{ marginRight: 6 }}>未读</Tag>}
                  {n.title}
                </span>
              }
              description={
                <>
                  <div style={{ color: '#555', marginBottom: 4 }}>{n.content}</div>
                  <Text type="secondary" style={{ fontSize: 12 }}>{n.createdAt}</Text>
                </>
              }
            />
          </List.Item>
        )}
      />
    </Drawer>
  )
}
