import { useAuthStore } from '@/store/auth'
import StudentDashboard from './StudentDashboard'
import CounsellorDashboard from './CounsellorDashboard'
import DeanDashboard from './DeanDashboard'

/** 角色路由：同一 /dashboard 按角色渲染不同看板 */
export default function Dashboard() {
  const role = useAuthStore((s) => s.user?.role)
  if (role === 'Counsellor') return <CounsellorDashboard />
  if (role === 'Dean') return <DeanDashboard />
  return <StudentDashboard />
}
