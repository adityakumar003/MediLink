/**
 * src/pages/doctor/DoctorDashboard.tsx
 * Doctor sections served as separate sidebar pages:
 * overview (dashboard) | requests | patients.
 */
import { useEffect, useState, type FC } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import DoctorLayout from '../../layouts/DoctorLayout'
import { useAuth } from '../../hooks/useAuth'
import {
  getMyProfile,
  getPendingRequests,
  respondToRequest,
  getMyPatients,
  updateMyProfile,
} from '../../services/doctorService'
import type { DoctorProfile, PatientRequestItem, PatientSummary } from '../../types/doctor.types'
import RequestCard from '../../components/doctor/RequestCard'
import PatientList from '../../components/doctor/PatientList'
import PatientReportView from '../../components/doctor/PatientReportView'
import LoadingSpinner from '../../components/common/LoadingSpinner'
import ChatWindow from '../../components/common/ChatWindow'
import Icon from '../../components/common/Icon'
import { AvatarWithUpload } from '../../components/common/Avatar'
import ParameterTrend from '../../components/analytics/ParameterTrend'
import { buildTrends } from '../../components/analytics/trends'
import { getPatientReports } from '../../services/doctorService'
import { getAnalysis } from '../../services/reportService'
import type { AnalysisResult } from '../../types/report.types'

export type DoctorSection = 'overview' | 'requests' | 'patients' | 'analytics'

interface DoctorDashboardProps {
  section: DoctorSection
}

const DoctorDashboard: FC<DoctorDashboardProps> = ({ section }) => {
  const { user, token, login } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [profile, setProfile] = useState<DoctorProfile | null>(null)
  const [requests, setRequests] = useState<PatientRequestItem[]>([])
  const [patients, setPatients] = useState<PatientSummary[]>([])
  const [selectedPatient, setSelectedPatient] = useState<PatientSummary | null>(null)
  const [loadingInit, setLoadingInit] = useState(true)
  const [respondingId, setRespondingId] = useState<string | null>(null)
  const [savingLocation, setSavingLocation] = useState(false)
  const [locationMessage, setLocationMessage] = useState('')
  const [photoKey, setPhotoKey] = useState(0)
  const [analyticsPatientId, setAnalyticsPatientId] = useState<string | null>(null)
  const [trendAnalyses, setTrendAnalyses] = useState<AnalysisResult[]>([])
  const [loadingTrends, setLoadingTrends] = useState(false)
  const [patientView, setPatientView] = useState<'reports' | 'chat'>('reports')

  const handlePhotoChanged = (hasPhoto: boolean) => {
    setPhotoKey(k => k + 1)
    if (user && token) login(token, { ...user, has_photo: hasPhoto })
  }

  const loadData = async () => {
    try {
      const [prof, reqs, pts] = await Promise.all([
        getMyProfile(),
        getPendingRequests(),
        getMyPatients(),
      ])
      setProfile(prof)
      setRequests(reqs)
      setPatients(pts)
      if (section === 'patients') {
        const wantedId = (location.state as { patientId?: string } | null)?.patientId
        setSelectedPatient(pts.find(p => p.user_id === wantedId) ?? null)
      }
      if (section === 'analytics' && pts.length > 0) {
        const wantedId = (location.state as { patientId?: string } | null)?.patientId
        const targetId = pts.some(p => p.user_id === wantedId) ? wantedId! : pts[0].user_id
        loadPatientTrends(targetId)
      }
    } catch { /* ignore */ }
    finally { setLoadingInit(false) }
  }

  useEffect(() => { loadData() }, [section])

  const handleRespond = async (requestId: string, accept: boolean) => {
    setRespondingId(requestId)
    try {
      await respondToRequest(requestId, accept)
      await loadData()  // refresh
    } catch { /* ignore */ }
    finally { setRespondingId(null) }
  }

  const handleSaveCurrentLocation = () => {
    setLocationMessage('')
    if (!('geolocation' in navigator)) {
      setLocationMessage('Location services are not available in this browser.')
      return
    }

    setSavingLocation(true)
    navigator.geolocation.getCurrentPosition(
      async position => {
        try {
          const { latitude, longitude } = position.coords
          const updated = await updateMyProfile({ latitude, longitude })
          setProfile(updated)
          setLocationMessage('Practice location saved.')
        } catch {
          setLocationMessage('Unable to save location.')
        } finally {
          setSavingLocation(false)
        }
      },
      () => {
        setLocationMessage('Allow location access to save your practice location.')
        setSavingLocation(false)
      },
      { enableHighAccuracy: true, timeout: 10000 },
    )
  }

  const loadPatientTrends = async (patientId: string) => {
    setAnalyticsPatientId(patientId)
    setLoadingTrends(true)
    try {
      const reps = await getPatientReports(patientId)
      const results = await Promise.all(
        reps.filter(r => r.has_analysis).map(r => getAnalysis(r.id).catch(() => null)),
      )
      setTrendAnalyses(results.filter((a): a is AnalysisResult => a !== null))
    } catch { /* ignore */ }
    setLoadingTrends(false)
  }

  const handleSelectPatient = (id: string) => {
    const p = patients.find(pt => pt.user_id === id) ?? null
    if (section === 'patients') {
      setSelectedPatient(p)
      setPatientView('reports')
    } else {
      navigate('/doctor/patients', { state: { patientId: id } })
    }
  }

  if (loadingInit) return (
    <DoctorLayout>
      <div className="flex items-center justify-center h-64">
        <LoadingSpinner size="lg" label="Loading dashboard…" />
      </div>
    </DoctorLayout>
  )

  return (
    <DoctorLayout>
      <div className="max-w-5xl mx-auto">
        {/* Header */}
        <div className="mb-6 flex items-center gap-4">
          <AvatarWithUpload
            name={user?.full_name ?? 'Doctor'}
            hasPhoto={user?.has_photo}
            refreshKey={photoKey}
            onChanged={handlePhotoChanged}
            className="w-14 h-14 text-xl"
          />
          <div>
            <h1 className="page-title">
              Dr. {user?.full_name?.split(' ').slice(-1)[0]}
            </h1>
            {profile && (
              <div className="flex items-center gap-3 mt-1">
                <span className="badge bg-blue-50 text-blue-700 font-mono">{profile.doctor_id}</span>
                <span className="text-sm text-slate-500">{profile.specialization}</span>
                {profile.hospital && <span className="text-sm text-slate-400">· {profile.hospital}</span>}
              </div>
            )}
          </div>
        </div>

        {/* ── OVERVIEW ── */}
        {section === 'overview' && (
          <div>
            {/* Stats */}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-6">
              {[
                { label: 'Connected Patients', value: patients.length, icon: 'users' as const },
                { label: 'Pending Requests', value: requests.length, icon: 'clock' as const },
                { label: 'Experience', value: profile ? `${profile.experience}y` : '—', icon: 'activity' as const },
              ].map(s => (
                <div key={s.label} className="card !p-5 flex items-center gap-4">
                  <span className="stat-tile">
                    <Icon name={s.icon} className="w-5 h-5" />
                  </span>
                  <div>
                    <p className="text-2xl font-bold text-slate-900 leading-none">{s.value}</p>
                    <p className="text-sm text-slate-500 mt-1">{s.label}</p>
                  </div>
                </div>
              ))}
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
              {/* Profile */}
              <div className="lg:col-span-1">
                <div className="card">
                  <h3 className="font-semibold text-slate-800 mb-4">My Profile</h3>
                  {profile && (
                    <div className="flex flex-col gap-2 text-sm">
                      <Row label="Name" value={profile.full_name} />
                      <Row label="Email" value={profile.email} />
                      <Row label="Doctor ID" value={profile.doctor_id} />
                      <Row label="Specialization" value={profile.specialization} />
                      <Row label="Experience" value={`${profile.experience} years`} />
                      {profile.hospital && <Row label="Hospital" value={profile.hospital} />}
                      {profile.phone && <Row label="Phone" value={profile.phone} />}
                    </div>
                  )}
                  <div className="mt-4 pt-3 border-t border-slate-200">
                    <p className="text-xs text-slate-400">
                      Share your Doctor ID (<strong className="font-mono text-blue-600">{profile?.doctor_id}</strong>) with patients so they can connect with you.
                    </p>
                  </div>
                  <div className="mt-4 pt-3 border-t border-slate-200">
                    <div className="flex items-center justify-between gap-3">
                      <div>
                        <p className="text-sm font-medium text-slate-700">Practice location</p>
                        <p className="text-xs text-slate-400">
                          {profile?.latitude && profile?.longitude
                            ? `${profile.latitude.toFixed(4)}, ${profile.longitude.toFixed(4)}`
                            : 'No GPS location saved'}
                        </p>
                      </div>
                      <button
                        onClick={handleSaveCurrentLocation}
                        disabled={savingLocation}
                        className="btn-secondary btn-sm shrink-0"
                      >
                        {savingLocation ? <LoadingSpinner size="sm" /> : 'Use GPS'}
                      </button>
                    </div>
                    {locationMessage && <p className="text-xs text-slate-500 mt-2">{locationMessage}</p>}
                  </div>
                </div>
              </div>

              {/* Recent requests + patients */}
              <div className="lg:col-span-2 flex flex-col gap-4">
                {requests.length > 0 && (
                  <div className="card">
                    <div className="section-header">
                      <h3 className="font-semibold text-slate-800">Pending Requests</h3>
                      <button onClick={() => navigate('/doctor/requests')} className="text-xs text-blue-600 hover:underline">
                        View all
                      </button>
                    </div>
                    <div className="flex flex-col gap-2">
                      {requests.slice(0, 2).map(r => (
                        <RequestCard key={r.request_id} request={r}
                          onAccept={id => handleRespond(id, true)}
                          onReject={id => handleRespond(id, false)}
                          loading={respondingId === r.request_id} />
                      ))}
                    </div>
                  </div>
                )}

                <div className="card">
                  <div className="section-header">
                    <h3 className="font-semibold text-slate-800">My Patients</h3>
                    <button onClick={() => navigate('/doctor/patients')} className="text-xs text-blue-600 hover:underline">
                      View all
                    </button>
                  </div>
                  <PatientList
                    patients={patients.slice(0, 4)}
                    selectedId={selectedPatient?.user_id}
                    onSelect={handleSelectPatient}
                  />
                </div>
              </div>
            </div>
          </div>
        )}

        {/* ── REQUESTS ── */}
        {section === 'requests' && (
          <div className="card">
            <h3 className="font-semibold text-slate-800 mb-4">
              Patient Requests ({requests.length})
            </h3>
            {requests.length === 0 ? (
              <p className="text-sm text-slate-400 py-6 text-center">No pending requests.</p>
            ) : (
              <div className="flex flex-col gap-3">
                {requests.map(r => (
                  <RequestCard key={r.request_id} request={r}
                    onAccept={id => handleRespond(id, true)}
                    onReject={id => handleRespond(id, false)}
                    loading={respondingId === r.request_id} />
                ))}
              </div>
            )}
          </div>
        )}

        {/* ── PATIENTS ── */}
        {section === 'patients' && (
          <div className="grid grid-cols-1 lg:grid-cols-5 gap-5">
            <div className="lg:col-span-2 card">
              <h3 className="font-semibold text-slate-800 mb-3">Connected Patients</h3>
              <PatientList
                patients={patients}
                selectedId={selectedPatient?.user_id}
                onSelect={handleSelectPatient}
              />
            </div>
            <div className="lg:col-span-3 card">
              {selectedPatient ? (
                <div className="flex flex-col gap-4">
                  <div className="flex gap-1 bg-slate-100 p-1 rounded-full w-fit">
                    {(['reports', 'chat'] as const).map(tab => (
                      <button key={tab} onClick={() => setPatientView(tab)}
                        className={`px-4 py-1.5 rounded-full text-xs font-semibold capitalize transition-all
                          ${patientView === tab ? 'bg-white text-slate-800 shadow-sm' : 'text-slate-500 hover:text-slate-700'}`}>
                        {tab}
                      </button>
                    ))}
                  </div>
                  {patientView === 'reports' ? (
                    <PatientReportView
                      patientId={selectedPatient.user_id}
                      patientName={selectedPatient.full_name}
                    />
                  ) : (
                    <ChatWindow
                      receiverId={selectedPatient.user_id}
                      receiverName={selectedPatient.full_name}
                    />
                  )}
                </div>
              ) : (
                <div className="flex items-center justify-center h-40 text-slate-400 text-sm">
                  Select a patient to view their reports.
                </div>
              )}
            </div>
          </div>
        )}
        {/* ── ANALYTICS ── */}
        {section === 'analytics' && (
          <div>
            <div className="mb-5">
              <h1 className="page-title">Patient Analytics</h1>
              <p className="page-sub">Select a patient to see their key levels across reports.</p>
            </div>
            {patients.length === 0 ? (
              <div className="card text-center py-12 text-slate-400">
                <p className="font-medium text-slate-600">No connected patients yet</p>
                <p className="text-sm mt-1">Accept a connection request to view patient trends.</p>
              </div>
            ) : (
              <div className="grid grid-cols-1 lg:grid-cols-5 gap-5">
                <div className="lg:col-span-2 card !p-3">
                  <div className="flex flex-col gap-1">
                    {patients.map(p => (
                      <button
                        key={p.user_id}
                        onClick={() => loadPatientTrends(p.user_id)}
                        className={`history-row !cursor-pointer text-left w-full ${
                          analyticsPatientId === p.user_id ? '!bg-white !border-slate-200 shadow-sm' : ''
                        }`}
                      >
                        <span className="avatar w-9 h-9 text-xs">
                          {p.full_name.split(' ').map(w => w.charAt(0)).slice(0, 2).join('').toUpperCase()}
                        </span>
                        <span className="flex-1 min-w-0">
                          <span className="block font-medium text-slate-800 text-sm truncate">{p.full_name}</span>
                          <span className="block text-xs text-slate-400">{p.report_count} report{p.report_count === 1 ? '' : 's'}</span>
                        </span>
                        <Icon name="chevronRight" className="w-4 h-4 text-slate-300 shrink-0" />
                      </button>
                    ))}
                  </div>
                </div>
                <div className="lg:col-span-3">
                  {loadingTrends ? (
                    <div className="flex justify-center py-12"><LoadingSpinner label="Loading trends…" /></div>
                  ) : analyticsPatientId ? (
                    <ParameterTrend trends={buildTrends(trendAnalyses)} />
                  ) : (
                    <div className="card text-center py-12 text-slate-400 text-sm">
                      Select a patient to view their trends.
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </DoctorLayout>
  )
}

const Row: FC<{ label: string; value: string }> = ({ label, value }) => (
  <div className="flex justify-between gap-2">
    <span className="text-slate-500">{label}</span>
    <span className="font-medium text-slate-700 text-right break-all">{value}</span>
  </div>
)

export default DoctorDashboard
