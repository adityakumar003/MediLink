/**
 * src/layouts/PatientLayout.tsx
 * Floating glass sidebar + content area for patient pages.
 */
import type { FC, ReactNode } from 'react'
import { NavLink, useNavigate } from 'react-router-dom'
import { useAuth } from '../hooks/useAuth'
import { logout as apiLogout } from '../services/authService'
import Icon, { type IconName } from '../components/common/Icon'

const NAV: { label: string; path: string; icon: IconName }[] = [
  { label: 'Dashboard', path: '/patient/dashboard', icon: 'grid' },
  { label: 'Find a Doctor', path: '/patient/doctors', icon: 'search' },
  { label: 'Upload Report', path: '/patient/upload', icon: 'upload' },
  { label: 'History', path: '/patient/history', icon: 'clock' },
  { label: 'Analytics', path: '/patient/analytics', icon: 'trendingUp' },
  { label: 'Chats', path: '/patient/chats', icon: 'chat' },
  { label: 'Video', path: '/patient/consultations', icon: 'video' },
]

interface PatientLayoutProps { children: ReactNode }

const PatientLayout: FC<PatientLayoutProps> = ({ children }) => {
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
        <p className="sidebar-caption mt-6">Patient</p>
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
          <div className="pt-3 mt-2 border-t border-slate-200/70">
            <p className="text-[11px] text-slate-400 leading-relaxed px-1">
              AI analysis is informational only. Always consult a licensed physician.
            </p>
          </div>
        </div>
      </aside>

      {/* Main column */}
      <div className="flex-1 min-w-0 flex flex-col gap-4">
        {/* Mobile nav — sidebar is hidden on small screens */}
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

export default PatientLayout
