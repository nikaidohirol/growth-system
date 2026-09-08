import { useEffect, useMemo, useState } from 'react'
import { Outlet, useLocation, useNavigate } from 'react-router-dom'
import { Avatar, Badge, Dropdown, Layout, Menu, theme } from 'antd'
import type { MenuProps } from 'antd'
import {
  AuditOutlined, BellOutlined, DownOutlined, ExportOutlined, EyeOutlined, FileSearchOutlined,
  IdcardOutlined, LogoutOutlined, RobotOutlined, SoundOutlined, TeamOutlined, TrophyOutlined, UserOutlined,
} from '@ant-design/icons'
import { notificationAPI } from '@/api/modules'
import { useAuthStore } from '@/store/auth'
import AIChatDrawer from '@/components/chat/AIChatDrawer'
import NotificationDrawer from '@/components/layout/NotificationDrawer'

const { Sider, Header, Content } = Layout

type MenuEntry = NonNullable<MenuProps['items']>[number]

function useMenu(): MenuEntry[] {
  const { user } = useAuthStore()
  return useMemo(() => {
    if (user?.role === 'Student') {
      return [
        { key: '/dashboard', icon: <TrophyOutlined />, label: '主面板' },
        {
          key: 'practice', icon: <TeamOutlined />, label: '社会实践', children: [
            { key: '/entity/practice', label: '社会实践活动' },
            { key: '/entity/voluntary', label: '志愿服务活动' },
          ],
        },
        {
          key: 'inn', icon: <TrophyOutlined />, label: '创新创业', children: [
            { key: '/entity/inn_chair', label: '前沿学术报告' },
            { key: '/entity/inn_project', label: '年度创新创业项目' },
            { key: '/entity/inn_competition', label: '科技创新竞赛' },
            { key: '/entity/inn_enterprise', label: '创业实践' },
            { key: '/entity/inn_paper', label: '学术论文' },
            { key: '/entity/inn_patent', label: '申请专利' },
            { key: '/entity/inn_other', label: '其他实践活动' },
          ],
        },
        { key: '/entity/honor', icon: <TrophyOutlined />, label: '个人荣誉' },
        { key: '/entity/certificate', icon: <IdcardOutlined />, label: '技能证书' },
        { key: '/entity/organization', icon: <TeamOutlined />, label: '组织经历' },
        { key: '/entity/party', icon: <UserOutlined />, label: '入党情况' },
        { key: '/grade', icon: <TrophyOutlined />, label: '综合素质成绩' },
        { key: '/export', icon: <ExportOutlined />, label: '成长档案' },
        { key: '/publicity', icon: <SoundOutlined />, label: '院级公示栏' },
        { key: '/info', icon: <UserOutlined />, label: '个人信息' },
      ]
    }
    if (user?.role === 'Counsellor') {
      return [
        { key: '/dashboard', icon: <AuditOutlined />, label: '主面板' },
        { key: '/audit', icon: <AuditOutlined />, label: '审核中心' },
        { key: '/comp-rank', icon: <TrophyOutlined />, label: '综测测算排名' },
        { key: '/publicity', icon: <SoundOutlined />, label: '院级公示栏' },
        { key: '/students', icon: <TeamOutlined />, label: '学生管理' },
        { key: '/logs', icon: <FileSearchOutlined />, label: '操作日志' },
        { key: '/info', icon: <UserOutlined />, label: '个人信息' },
      ]
    }
    return [
      { key: '/dashboard', icon: <AuditOutlined />, label: '主面板' },
      { key: '/audit', icon: <AuditOutlined />, label: '审核中心' },
      { key: '/comp-rank', icon: <TrophyOutlined />, label: '综测测算排名' },
      { key: '/publicity', icon: <EyeOutlined />, label: '公示异议复核' },
      { key: '/logs', icon: <FileSearchOutlined />, label: '操作日志' },
      { key: '/info', icon: <UserOutlined />, label: '个人信息' },
    ]
  }, [user?.role])
}

export default function MainLayout() {
  const [collapsed, setCollapsed] = useState(false)
  const [chatOpen, setChatOpen] = useState(false)
  const [notifOpen, setNotifOpen] = useState(false)
  const [notifUnread, setNotifUnread] = useState(0)
  const navigate = useNavigate()
  const location = useLocation()
  const { user, logout } = useAuthStore()
  const { token } = theme.useToken()
  const menu = useMenu()

  // 未读数轮询（60s，页面切后台暂停）——SSE 推送对本系统低频使用场景收益有限
  useEffect(() => {
    if (!user) return
    let stop = false
    const tick = async () => {
      if (document.hidden) return
      try {
        const d = await notificationAPI.unread()
        if (!stop) setNotifUnread(d.unread)
      } catch { /* 轮询失败忽略，下轮再试 */ }
    }
    tick()
    const timer = setInterval(tick, 60000)
    return () => { stop = true; clearInterval(timer) }
  }, [user])

  const activeLabel = useMemo(() => {
    for (const m of menu) {
      if (m && 'key' in m && m.key === location.pathname) {
        return 'label' in m ? m.label : undefined
      }
    }
    return undefined
  }, [menu, location.pathname])

  const roleLabel = { Student: '学生', Counsellor: '辅导员', Dean: '院长' }[user?.role ?? 'Student']

  return (
    <Layout style={{ height: '100vh' }}>
      <Sider collapsible collapsed={collapsed} onCollapse={setCollapsed} theme="dark">
        <div style={{
          height: 56, display: 'flex', alignItems: 'center', justifyContent: 'center',
          color: '#fff', fontWeight: 700, fontSize: collapsed ? 14 : 16, letterSpacing: 1,
        }}>
          {collapsed ? 'GS' : 'AI 学生成长发展系统'}
        </div>
        <Menu
          theme="dark" mode="inline" selectedKeys={[location.pathname]}
          items={menu}
          onClick={({ key }) => {
            if (String(key).startsWith('/')) navigate(String(key))
          }}
        />
      </Sider>
      <Layout>
        <Header style={{
          background: '#fff', padding: '0 20px', display: 'flex',
          alignItems: 'center', justifyContent: 'space-between',
          boxShadow: '0 1px 4px rgba(0,21,41,.08)',
        }}>
          <span style={{ fontSize: 15, color: token.colorTextSecondary }}>
            {activeLabel ?? location.pathname.replace('/entity/', '').replace('/', '')}
          </span>
          <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
            <Badge count={notifUnread} size="small" overflowCount={99}>
              <BellOutlined
                data-testid="notification-bell"
                style={{ fontSize: 19, color: token.colorTextSecondary, cursor: 'pointer' }}
                onClick={() => setNotifOpen(true)}
              />
            </Badge>
            <Badge dot={user?.role === 'Student'} title="AI 助手">
              <RobotOutlined
                data-testid="ai-entry"
                style={{ fontSize: 20, color: token.colorPrimary, cursor: 'pointer' }}
                onClick={() => setChatOpen(true)}
              />
            </Badge>
            <Dropdown
              menu={{
                items: [
                  { key: 'info', icon: <UserOutlined />, label: '个人信息' },
                  { type: 'divider' },
                  { key: 'logout', icon: <LogoutOutlined />, label: '退出登录' },
                ],
                onClick: ({ key }) => {
                  if (key === 'logout') {
                    logout()
                    navigate('/login')
                  } else if (key === 'info') navigate('/info')
                },
              }}
            >
              <span style={{ cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 8 }}>
                <Avatar size={30} icon={<UserOutlined />} src={user?.photo} />
                <span>
                  {user?.name}
                  <span style={{ color: '#999', fontSize: 12, marginLeft: 6 }}>{roleLabel}</span>
                </span>
                <DownOutlined style={{ fontSize: 10, color: '#999' }} />
              </span>
            </Dropdown>
          </div>
        </Header>
        <Content style={{ margin: 16, overflow: 'auto' }}>
          <Outlet />
        </Content>
      </Layout>
      {user && <AIChatDrawer open={chatOpen} onClose={() => setChatOpen(false)} />}
      {user && (
        <NotificationDrawer
          open={notifOpen}
          unread={notifUnread}
          onClose={() => setNotifOpen(false)}
          onChanged={setNotifUnread}
        />
      )}
    </Layout>
  )
}
