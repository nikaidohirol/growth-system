import { Suspense, lazy } from 'react'
import { Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { Spin } from 'antd'
import { useAuthStore } from '@/store/auth'
import { useMetaStore } from '@/store/meta'
import MainLayout from '@/components/layout/MainLayout'
import Login from '@/pages/Login'
import type { Role } from '@/types'

// 路由级代码分割：echarts / xlsx / jspdf / html2canvas 等重依赖按需加载
const NotFound = lazy(() => import('@/pages/NotFound'))
const Dashboard = lazy(() => import('@/pages/dashboard/Dashboard'))
const EntityPage = lazy(() => import('@/pages/student/EntityPage'))
const GradePage = lazy(() => import('@/pages/student/GradePage'))
const ExportPage = lazy(() => import('@/pages/student/ExportPage'))
const AuditCenter = lazy(() => import('@/pages/counsellor/AuditCenter'))
const StudentManage = lazy(() => import('@/pages/counsellor/StudentManage'))
const CompRankingPage = lazy(() => import('@/pages/counsellor/CompRankingPage'))
const OpLogPage = lazy(() => import('@/pages/counsellor/OpLogPage'))
const PublicityBoard = lazy(() => import('@/pages/common/PublicityBoard'))
const InfoPage = lazy(() => import('@/pages/info/InfoPage'))

function PageFallback() {
  return <Spin size="large" style={{ display: 'grid', placeItems: 'center', height: '60vh' }} />
}

function Guard({ roles, children }: { roles?: Role[]; children: JSX.Element }) {
  const { token, user } = useAuthStore()
  const location = useLocation()
  if (!token) return <Navigate to="/login" state={{ from: location.pathname }} replace />
  if (roles && user && !roles.includes(user.role)) return <Navigate to="/dashboard" replace />
  return children
}

/** 登录后预取字典与实体契约，并做角色默认跳转 */
function Bootstrap({ children }: { children: JSX.Element }) {
  const { token, user } = useAuthStore()
  const { loaded, load } = useMetaStore()
  if (token && !loaded) {
    load().catch(() => undefined)
  }
  if (token && !user) {
    return (
      <div style={{ display: 'grid', placeItems: 'center', height: '100vh' }}>
        <Spin size="large" tip="加载中..." />
      </div>
    )
  }
  return children
}

export default function App() {
  return (
    <Suspense fallback={<PageFallback />}>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/" element={<Guard><Bootstrap><MainLayout /></Bootstrap></Guard>}>
          <Route index element={<Navigate to="/dashboard" replace />} />
          <Route path="dashboard" element={<Dashboard />} />
          {/* 13 类实体由注册表契约驱动，一个路由通吃 */}
          <Route path="entity/:key" element={<Guard roles={['Student']}><EntityPage /></Guard>} />
          <Route path="grade" element={<Guard roles={['Student']}><GradePage /></Guard>} />
          <Route path="export" element={<Guard roles={['Student']}><ExportPage /></Guard>} />
          <Route path="audit" element={<Guard roles={['Counsellor', 'Dean']}><AuditCenter /></Guard>} />
          <Route path="comp-rank" element={<Guard roles={['Counsellor', 'Dean']}><CompRankingPage /></Guard>} />
          <Route path="students" element={<Guard roles={['Counsellor', 'Dean']}><StudentManage /></Guard>} />
          <Route path="logs" element={<Guard roles={['Counsellor', 'Dean']}><OpLogPage /></Guard>} />
          <Route path="publicity" element={<PublicityBoard />} />
          <Route path="info" element={<InfoPage />} />
          <Route path="*" element={<NotFound />} />
        </Route>
      </Routes>
    </Suspense>
  )
}
