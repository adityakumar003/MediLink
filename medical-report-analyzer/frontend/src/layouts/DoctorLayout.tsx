/**
 * src/layouts/DoctorLayout.tsx
 * Floating glass sidebar + content area for doctor pages.
 */
import type { FC, ReactNode } from 'react'
import { NavLink, useNavigate } from 'react-router-dom'
import { useAuth } from '../hooks/useAuth'
import { logout as apiLogout } from '../services/authService'
import Icon, { type IconName } from '../components/common/Icon'

const NAV: { label: string; path: string; icon: IconName }[] = [
  { label: 'Dashboard', path: '/doctor/dashboard', icon: 'grid' },
  { label: 'Requests', path: '/doctor/requests', icon: 'users' },
  { label: 'Patients', path: '/doctor/patients', icon: 'user' },
  { label: 'Video', path: '/doctor/consultations', icon: 'video' },
  { label: 'Analytics', path: '/doctor/analytics', icon: 'trendingUp' },
]

interface DoctorLayoutProps { children: ReactNode }

const DoctorLayout: FC<DoctorLayoutProps> = ({ children }) => {
  const { logout } = useAuth()
  const navigate = useNavigate()

  const handleSignOut = async () => {
    try { await apiLogout() } catch { /* ignore */ }
    logout()
    navigate('/login')
  }

  return (
    <div className="min-h-screen flex gap-4 p-4">
      {/* Sidebar */}
      <aside className="sidebar-shell hidden md:flex flex-col w-60 rounded-3xl p-5 shrink-0 sticky top-4 h-[calc(100vh-2rem)]">
        <div className="flex items-center gap-2.5 px-1">
          <span className="logo-mark">
            <Icon name="activity" className="w-5 h-5" />
          </span>
          <span className="font-bold text-lg text-slate-900 tracking-tight">MediBridge</span>
        </div>
        <p className="sidebar-caption mt-6">Doctor</p>
        <nav className="flex flex-col gap-1">
          {NAV.map(item => (
            <NavLink key={item.path} to={item.path}
              className={({ isActive }) => `sidebar-link ${isActive ? 'active' : ''}`}>
              <Icon name={item.icon} className="w-4 h-4" />
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="mt-auto flex flex-col gap-1">
          <button onClick={handleSignOut} className="sidebar-link w-full text-left">
            <Icon name="logout" className="w-4 h-4" />
            Sign out
          </button>
        </div>
      </aside>

      {/* Main column */}
      <div className="flex-1 min-w-0 flex flex-col gap-4">
        <nav className="sidebar-shell md:hidden flex gap-1 rounded-2xl px-3 py-2 overflow-x-auto">
          {NAV.map(item => (
            <NavLink key={item.path} to={item.path}
              className={({ isActive }) => `sidebar-link shrink-0 ${isActive ? 'active' : ''}`}>
              {item.label}
            </NavLink>
          ))}
        </nav>
        <main className="flex-1 overflow-auto">{children}</main>
      </div>
    </div>
  )
}

export default DoctorLayout
