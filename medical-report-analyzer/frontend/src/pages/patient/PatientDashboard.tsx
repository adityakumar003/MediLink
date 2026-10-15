/**
 * src/pages/patient/PatientDashboard.tsx
 * Patient sections served as separate sidebar pages:
 * overview (dashboard) | doctors (find & connect) | upload | history.
 */
import { useEffect, useState, type FC } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import PatientLayout from '../../layouts/PatientLayout'
import { useAuth } from '../../hooks/useAuth'
import { getMyProfile, getMyDoctorRequests } from '../../services/patientService'
import { listMyReports, getAnalysis, deleteReport } from '../../services/reportService'
import type { PatientProfile, DoctorRequestStatus } from '../../types/patient.types'
import type { ReportListItem, AnalysisResult } from '../../types/report.types'
import DoctorSearch from '../../components/patient/DoctorSearch'
import ReportUpload from '../../components/patient/ReportUpload'
import AnalysisSummary from '../../components/patient/AnalysisSummary'
import LoadingSpinner from '../../components/common/LoadingSpinner'
import ChatWindow from '../../components/common/ChatWindow'
import Icon from '../../components/common/Icon'
import { AvatarWithUpload } from '../../components/common/Avatar'
import ParameterTrend from '../../components/analytics/ParameterTrend'
import { buildTrends } from '../../components/analytics/trends'

export type PatientSection = 'overview' | 'doctors' | 'upload' | 'history' | 'analytics' | 'chats'

interface PatientDashboardProps {
  section: PatientSection
}

const PatientDashboard: FC<PatientDashboardProps> = ({ section }) => {
  const { user, token, login } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [profile, setProfile] = useState<PatientProfile | null>(null)
  const [requests, setRequests] = useState<DoctorRequestStatus[]>([])
  const [reports, setReports] = useState<ReportListItem[]>([])
  const [selectedAnalysis, setSelectedAnalysis] = useState<AnalysisResult | null>(null)
  const [loadingInit, setLoadingInit] = useState(true)
  const [loadingAnalysis, setLoadingAnalysis] = useState(false)
  const [deletingId, setDeletingId] = useState<string | null>(null)
  const [photoKey, setPhotoKey] = useState(0)
  const [trendAnalyses, setTrendAnalyses] = useState<AnalysisResult[]>([])
  const [loadingTrends, setLoadingTrends] = useState(false)
  const [chatDoctorId, setChatDoctorId] = useState<string | null>(null)

  const handlePhotoChanged = (hasPhoto: boolean) => {
    setPhotoKey(k => k + 1)
    if (user && token) login(token, { ...user, has_photo: hasPhoto })
  }

  const loadData = async () => {
    try {
      const [prof, reqs, reps] = await Promise.all([
        getMyProfile(),
        getMyDoctorRequests(),
        listMyReports(),
      ])
      setProfile(prof)
      setRequests(reqs)
      setReports(reps)
      // Load all analyses for the analytics section
      if (section === 'analytics') {
        setLoadingTrends(true)
        try {
          const withAnalysis = reps.filter(r => r.has_analysis)
          const results = await Promise.all(
            withAnalysis.map(r => getAnalysis(r.id).catch(() => null)),
          )
          setTrendAnalyses(results.filter((a): a is AnalysisResult => a !== null))
        } catch { /* ignore */ }
        setLoadingTrends(false)
      }
      // Auto-load analysis on the overview page
      if (section === 'overview') {
        const wantedId = (location.state as { reportId?: string } | null)?.reportId
        const target = reps.find(r => r.id === wantedId && r.has_analysis)
          ?? reps.find(r => r.has_analysis)
        if (target) {
          setLoadingAnalysis(true)
          try {
            const result = await getAnalysis(target.id)
            setSelectedAnalysis(result)
          } catch { /* ignore */ }
          setLoadingAnalysis(false)
        } else {
          setSelectedAnalysis(null)
        }
      }
    } catch { /* ignore */ }
    finally { setLoadingInit(false) }
  }

  useEffect(() => { loadData() }, [section])

  const handleUploaded = () => {
    // Reload everything after upload, then show the fresh analysis
    setTimeout(() => navigate('/patient/dashboard'), 1000)
  }

  const handleOpenReport = async (reportId: string, hasAnalysis: boolean) => {
    if (!hasAnalysis) return
    navigate('/patient/dashboard', { state: { reportId } })
  }

  const handleDeleteFailed = async (reportId: string) => {
    if (!window.confirm('Delete this failed report? This cannot be undone.')) return
    setDeletingId(reportId)
    try {
      await deleteReport(reportId)
      setReports(prev => prev.filter(r => r.id !== reportId))
    } catch { /* ignore — row stays so the user can retry */ }
    finally { setDeletingId(null) }
  }

  const connectedDoctors = requests.filter(r => r.status === 'accepted')
  const pendingRequests  = requests.filter(r => r.status === 'pending')

  if (loadingInit) return (
    <PatientLayout>
      <div className="flex items-center justify-center h-64"><LoadingSpinner size="lg" label="Loading dashboard…" /></div>
    </PatientLayout>
  )

  return (
    <PatientLayout>
      <div className="max-w-5xl mx-auto">
        {/* Page header */}
        <div className="mb-6 flex items-start justify-between gap-4 flex-wrap">
          <div>
            {section === 'overview' && (
              <>
                <h1 className="page-title">Good day, {user?.full_name?.split(' ')[0]}</h1>
                <p className="page-sub">Here is the latest analysis of your lab reports.</p>
              </>
            )}
            {section === 'doctors' && (
              <>
                <h1 className="page-title">Find a Doctor</h1>
                <p className="page-sub">Search by Doctor ID or discover doctors near you.</p>
              </>
            )}
            {section === 'upload' && (
              <>
                <h1 className="page-title">Upload Report</h1>
                <p className="page-sub">PDF, JPG or PNG · up to 10 MB</p>
              </>
            )}
            {section === 'history' && (
              <>
                <h1 className="page-title">Report History</h1>
                <p className="page-sub">{reports.length} report{reports.length === 1 ? '' : 's'}</p>
              </>
            )}
            {section === 'analytics' && (
              <>
                <h1 className="page-title">Analytics</h1>
                <p className="page-sub">Your key levels across past reports.</p>
              </>
            )}
            {section === 'chats' && (
              <>
                <h1 className="page-title">Chats</h1>
                <p className="page-sub">Chat with your connected doctors.</p>
              </>
            )}
          </div>
          {(section === 'overview' || section === 'history') && (
            <button onClick={() => navigate('/patient/upload')} className="btn-primary">
              <Icon name="upload" className="w-4 h-4" /> Upload report
            </button>
          )}
        </div>

        {/* ── OVERVIEW ── */}
        {section === 'overview' && (
          <div>
            {/* Stats bar */}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-6">
              {[
                { label: 'Reports', value: reports.length, icon: 'file' as const },
                { label: 'Connected Doctors', value: connectedDoctors.length, icon: 'users' as const },
                { label: 'Pending Requests', value: pendingRequests.length, icon: 'clock' as const },
              ].map(stat => (
                <div key={stat.label} className="card !p-5 flex items-center gap-4">
                  <span className="stat-tile">
                    <Icon name={stat.icon} className="w-5 h-5" />
                  </span>
                  <div>
                    <p className="text-2xl font-bold text-slate-900 leading-none">{stat.value}</p>
                    <p className="text-sm text-slate-500 mt-1">{stat.label}</p>
                  </div>
                </div>
              ))}
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
              {/* Left column — profile */}
              <div className="lg:col-span-1 flex flex-col gap-4">
                <div className="card">
                  {profile && (
                    <div className="flex items-center gap-3 mb-4">
                      <AvatarWithUpload
                        name={profile.full_name}
                        hasPhoto={user?.has_photo}
                        refreshKey={photoKey}
                        onChanged={handlePhotoChanged}
                        className="w-12 h-12 text-lg"
                      />
                      <div className="min-w-0">
                        <p className="font-semibold text-slate-900 truncate">{profile.full_name}</p>
                        <p className="text-xs text-slate-500 truncate">{profile.email}</p>
                      </div>
                    </div>
                  )}
                  <div className="grid grid-cols-3 gap-2 text-center">
                    {[
                      { label: 'Age', value: profile?.age ? `${profile.age}` : '—' },
                      { label: 'Gender', value: profile?.gender ? profile.gender.charAt(0).toUpperCase() + profile.gender.slice(1) : '—' },
                      { label: 'Blood', value: profile?.blood_group ?? '—' },
                    ].map(tile => (
                      <div key={tile.label} className="rounded-xl bg-white/70 border border-slate-200/60 px-2 py-2.5">
                        <p className="text-[11px] text-slate-400">{tile.label}</p>
                        <p className="text-sm font-semibold text-slate-800 mt-0.5">{tile.value}</p>
                      </div>
                    ))}
                  </div>
                  {profile?.phone && (
                    <p className="text-xs text-slate-500 mt-3">Phone: {profile.phone}</p>
                  )}
                </div>
              </div>

              {/* Right column — analysis */}
              <div className="lg:col-span-2">
                {loadingAnalysis && (
                  <div className="flex justify-center py-12"><LoadingSpinner label="Loading analysis…" /></div>
                )}
                {!loadingAnalysis && selectedAnalysis && (
                  <AnalysisSummary analysis={selectedAnalysis} />
                )}
                {!loadingAnalysis && !selectedAnalysis && (
                  <div className="card text-center py-12 text-slate-400">
                    <span className="mx-auto mb-3 w-12 h-12 rounded-xl bg-slate-100 text-slate-400 flex items-center justify-center">
                      <Icon name="file" className="w-6 h-6" />
                    </span>
                    <p className="font-medium text-slate-600">No analysis yet</p>
                    <p className="text-sm mt-1">Upload a PDF medical report to get an AI-powered analysis.</p>
                    <button onClick={() => navigate('/patient/upload')} className="btn-primary mt-4">
                      Upload Report
                    </button>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* ── FIND A DOCTOR ── */}
        {section === 'doctors' && (
          <div className="max-w-4xl flex flex-col gap-5">
            <DoctorSearch />
            <div className="card">
              <h3 className="font-semibold text-slate-900 text-lg mb-3">Pending Requests</h3>
              {pendingRequests.length > 0 ? (
                <div className="flex flex-col gap-2">
                  {pendingRequests.map(r => (
                    <div key={r.request_id} className="flex items-center gap-2 text-sm">
                      <span className="badge-pending">Pending</span>
                      <span className="text-slate-600 truncate">{r.doctor_name}</span>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-slate-400">
                  No pending requests. Accepted doctors appear under Chats.
                </p>
              )}
            </div>
          </div>
        )}

        {/* ── UPLOAD ── */}
        {section === 'upload' && (
          <div className="max-w-3xl">
            <ReportUpload onUploaded={handleUploaded} />
          </div>
        )}

        {/* ── HISTORY ── */}
        {section === 'history' && (
          <div className="card">
            <h3 className="font-semibold text-slate-800 mb-4">Report History</h3>
            {reports.length === 0 ? (
              <p className="text-sm text-slate-400 py-6 text-center">No reports uploaded yet.</p>
            ) : (
              <div className="flex flex-col gap-2">
                {reports.map(r => (
                  <div key={r.id}
                    className="history-row"
                    onClick={() => handleOpenReport(r.id, r.has_analysis)}>
                    <span className="avatar w-10 h-10 !text-sm">
                      <Icon name="file" className="w-4 h-4" />
                    </span>
                    <div className="flex-1 min-w-0">
                      <p className="font-medium text-slate-800 text-sm truncate">{r.original_filename}</p>
                      <p className="text-xs text-slate-400">{new Date(r.uploaded_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })}</p>
                    </div>
                    <span className={`badge shrink-0 ${
                      r.status === 'analyzed' ? 'badge-analyzed' :
                      r.status === 'failed'   ? 'badge-failed' : 'badge-uploaded'
                    }`}>{r.status === 'analyzed' ? 'Analyzed' : r.status === 'failed' ? 'Failed' : r.status}</span>
                    {r.status === 'failed' ? (
                      <button
                        onClick={e => { e.stopPropagation(); handleDeleteFailed(r.id) }}
                        disabled={deletingId === r.id}
                        title="Delete this failed report"
                        className="shrink-0 text-slate-400 hover:text-red-600 disabled:opacity-50 p-1.5"
                      >
                        <Icon name="trash" className="w-4 h-4" />
                      </button>
                    ) : (
                      <Icon name="chevronRight" className="w-4 h-4 text-slate-300 shrink-0" />
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
        {/* ── CHATS ── */}
        {section === 'chats' && (
          <div>
            {connectedDoctors.length === 0 ? (
              <div className="card text-center py-12 text-slate-400">
                <span className="mx-auto mb-3 w-12 h-12 rounded-full bg-blue-50 text-blue-600 flex items-center justify-center">
                  <Icon name="chat" className="w-6 h-6" />
                </span>
                <p className="font-medium text-slate-600">No connected doctors yet</p>
                <p className="text-sm mt-1">Find a doctor and send a connection request to start chatting.</p>
                <button onClick={() => navigate('/patient/doctors')} className="btn-primary mt-4">
                  Find a Doctor
                </button>
              </div>
            ) : (
              <div className="grid grid-cols-1 lg:grid-cols-5 gap-5">
                <div className="lg:col-span-2 card !p-3">
                  <div className="flex flex-col gap-1">
                    {connectedDoctors.map(r => (
                      <button
                        key={r.request_id}
                        onClick={() => setChatDoctorId(r.doctor_user_id)}
                        className={`history-row !cursor-pointer text-left w-full ${
                          chatDoctorId === r.doctor_user_id ? '!bg-white !border-slate-200 shadow-sm' : ''
                        }`}
                      >
                        <span className="avatar w-9 h-9 text-xs">
                          {r.doctor_name.split(' ').map(w => w.charAt(0)).slice(0, 2).join('').toUpperCase()}
                        </span>
                        <span className="flex-1 min-w-0">
                          <span className="block font-medium text-slate-800 text-sm truncate">Dr. {r.doctor_name}</span>
                          <span className="block text-xs text-slate-400 truncate">{r.doctor_specialization}</span>
                        </span>
                        <span className="badge-accepted shrink-0">Connected</span>
                      </button>
                    ))}
                  </div>
                </div>
                <div className="lg:col-span-3">
                  {(() => {
                    const active = connectedDoctors.find(r => r.doctor_user_id === chatDoctorId)
                    if (!active) {
                      return (
                        <div className="card text-center py-12 text-slate-400 text-sm">
                          Select a doctor to start chatting.
                        </div>
                      )
                    }
                    return (
                      <ChatWindow
                        key={active.doctor_user_id}
                        receiverId={active.doctor_user_id}
                        receiverName={`Dr. ${active.doctor_name}`}
                      />
                    )
                  })()}
                </div>
              </div>
            )}
          </div>
        )}

        {/* ── ANALYTICS ── */}
        {section === 'analytics' && (
          <div className="max-w-4xl">
            {loadingTrends ? (
              <div className="flex justify-center py-12"><LoadingSpinner label="Loading trends…" /></div>
            ) : (
              <ParameterTrend trends={buildTrends(trendAnalyses)} />
            )}
          </div>
        )}
      </div>
    </PatientLayout>
  )
}

export default PatientDashboard
