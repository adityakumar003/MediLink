/**
 * src/components/video/VideoConsultations.tsx
 * Video consultation list, doctor start/schedule form, and join actions.
 */
import { useCallback, useEffect, useMemo, useState, type FC } from 'react'
import { useNavigate } from 'react-router-dom'
import Icon from '../common/Icon'
import LoadingSpinner from '../common/LoadingSpinner'
import {
  cancelConsultation,
  listConsultations,
  scheduleConsultation,
  startConsultation,
  startScheduledConsultation,
} from '../../services/videoService'
import type { PatientSummary } from '../../types/doctor.types'
import type { Consultation, ConsultationStatus } from '../../types/video.types'

interface VideoConsultationsProps {
  role: 'patient' | 'doctor'
  patients?: PatientSummary[]
  compact?: boolean
}

const ACTIVE_STATUSES: ConsultationStatus[] = ['started', 'in_progress', 'scheduled']
const NO_PATIENTS: PatientSummary[] = []

const STATUS_ORDER: Record<ConsultationStatus, number> = {
  in_progress: 0,
  started: 1,
  scheduled: 2,
  completed: 3,
  cancelled: 4,
}

const STATUS_CLASSES: Record<ConsultationStatus, string> = {
  scheduled: 'badge bg-blue-100 text-blue-800',
  started: 'badge bg-amber-100 text-amber-800',
  in_progress: 'badge bg-emerald-100 text-emerald-800',
  completed: 'badge bg-slate-100 text-slate-600',
  cancelled: 'badge bg-red-100 text-red-700',
}

function apiErrorMessage(err: unknown, fallback: string): string {
  const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
  return typeof detail === 'string' && detail.trim() ? detail : fallback
}

function formatMoment(value?: string | null): string {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  return date.toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  })
}

function statusLabel(consultation: Consultation, role: 'patient' | 'doctor'): string {
  if (consultation.status === 'scheduled') return 'Scheduled'
  if (consultation.status === 'started') {
    return role === 'patient' ? 'Ready to join' : 'Waiting for patient'
  }
  if (consultation.status === 'in_progress') return 'In progress'
  if (consultation.status === 'completed') return 'Completed'
  return 'Cancelled'
}

function initials(name: string): string {
  return name.split(' ').map(part => part.charAt(0)).slice(0, 2).join('').toUpperCase() || '?'
}

function localDateTimeInputValue(date: Date): string {
  const pad = (value: number) => String(value).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`
}

const VideoConsultations: FC<VideoConsultationsProps> = ({
  role,
  patients = NO_PATIENTS,
  compact = false,
}) => {
  const navigate = useNavigate()
  const [consultations, setConsultations] = useState<Consultation[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [busyId, setBusyId] = useState<string | null>(null)
  const [patientId, setPatientId] = useState('')
  const [scheduledAt, setScheduledAt] = useState('')
  const [creating, setCreating] = useState<'start' | 'schedule' | null>(null)

  const sectionPath = role === 'doctor' ? '/doctor/consultations' : '/patient/consultations'
  const minDateTime = useMemo(
    () => localDateTimeInputValue(new Date(Date.now() + 5 * 60 * 1000)),
    [],
  )

  const load = useCallback(async () => {
    try {
      const items = await listConsultations()
      setConsultations(items)
      setError('')
    } catch (err) {
      setError(apiErrorMessage(err, 'Unable to load video consultations.'))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
    const timer = window.setInterval(load, 10000)
    return () => window.clearInterval(timer)
  }, [load])

  useEffect(() => {
    if (role !== 'doctor') return
    setPatientId(previous => (
      patients.some(patient => patient.user_id === previous)
        ? previous
        : (patients[0]?.user_id ?? '')
    ))
  }, [patients, role])

  const sorted = useMemo(() => (
    [...consultations].sort((left, right) => {
      const byStatus = STATUS_ORDER[left.status] - STATUS_ORDER[right.status]
      if (byStatus !== 0) return byStatus
      return Date.parse(right.created_at) - Date.parse(left.created_at)
    })
  ), [consultations])

  const activeConsultations = sorted.filter(item => ACTIVE_STATUSES.includes(item.status))
  const visible = compact ? activeConsultations.slice(0, 2) : sorted

  const handleStartNow = async () => {
    if (!patientId) {
      setError('Select a connected patient first.')
      return
    }
    setCreating('start')
    setError('')
    setNotice('')
    try {
      const consultation = await startConsultation(patientId)
      navigate(`/consultation/${consultation.id}`)
    } catch (err) {
      setError(apiErrorMessage(err, 'Could not start the consultation.'))
    } finally {
      setCreating(null)
    }
  }

  const handleSchedule = async () => {
    if (!patientId) {
      setError('Select a connected patient first.')
      return
    }
    if (!scheduledAt) {
      setError('Choose a date and time for the scheduled consultation.')
      return
    }
    const when = new Date(scheduledAt)
    if (Number.isNaN(when.getTime()) || when.getTime() <= Date.now()) {
      setError('Scheduled consultation time must be in the future.')
      return
    }

    setCreating('schedule')
    setError('')
    setNotice('')
    try {
      await scheduleConsultation(patientId, when.toISOString())
      setScheduledAt('')
      setNotice('Consultation scheduled. The patient will see it on their dashboard.')
      await load()
    } catch (err) {
      setError(apiErrorMessage(err, 'Could not schedule the consultation.'))
    } finally {
      setCreating(null)
    }
  }

  const handleStartScheduled = async (consultationId: string) => {
    setBusyId(consultationId)
    setError('')
    setNotice('')
    try {
      const consultation = await startScheduledConsultation(consultationId)
      navigate(`/consultation/${consultation.id}`)
    } catch (err) {
      setError(apiErrorMessage(err, 'Could not start the consultation.'))
    } finally {
      setBusyId(null)
    }
  }

  const handleCancel = async (consultationId: string) => {
    if (!window.confirm('Cancel this video consultation?')) return
    setBusyId(consultationId)
    setError('')
    setNotice('')
    try {
      await cancelConsultation(consultationId)
      await load()
    } catch (err) {
      setError(apiErrorMessage(err, 'Could not cancel the consultation.'))
    } finally {
      setBusyId(null)
    }
  }

  const renderCard = (consultation: Consultation) => {
    const otherName = consultation.other_participant_role === 'doctor'
      ? `Dr. ${consultation.other_participant_name}`
      : consultation.other_participant_name
    const isBusy = busyId === consultation.id

    return (
      <div
        key={consultation.id}
        className={`flex flex-col sm:flex-row sm:items-center gap-3 p-3 rounded-2xl border transition-colors ${
          consultation.status === 'in_progress' || consultation.status === 'started'
            ? 'border-blue-200 bg-blue-50/50'
            : 'border-slate-200 bg-white/70'
        }`}
      >
        <span className="avatar w-10 h-10 text-sm">{initials(otherName)}</span>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <p className="font-medium text-slate-800 text-sm truncate">{otherName}</p>
            <span className={STATUS_CLASSES[consultation.status]}>
              {statusLabel(consultation, role)}
            </span>
          </div>
          <p className="text-xs text-slate-500 mt-0.5">
            {consultation.other_participant_role === 'doctor' && consultation.doctor_specialization
              ? `${consultation.doctor_specialization} · `
              : ''}
            {consultation.status === 'scheduled' && consultation.scheduled_at
              ? `Scheduled ${formatMoment(consultation.scheduled_at)}`
              : consultation.status === 'completed' && consultation.ended_at
                ? `Ended ${formatMoment(consultation.ended_at)}`
                : consultation.started_at
                  ? `Started ${formatMoment(consultation.started_at)}`
                  : `Created ${formatMoment(consultation.created_at)}`}
          </p>
        </div>

        <div className="flex items-center gap-2 shrink-0 flex-wrap">
          {role === 'doctor' && consultation.can_start && (
            <button
              onClick={() => handleStartScheduled(consultation.id)}
              disabled={isBusy}
              className="btn-primary btn-sm"
            >
              {isBusy ? <LoadingSpinner size="sm" /> : <Icon name="video" className="w-4 h-4" />}
              Start
            </button>
          )}
          {consultation.can_join && (
            <button
              onClick={() => navigate(`/consultation/${consultation.id}`)}
              className="btn-primary btn-sm"
            >
              <Icon name="video" className="w-4 h-4" />
              {consultation.status === 'in_progress' ? 'Rejoin' : 'Join'}
            </button>
          )}
          {consultation.can_cancel && !compact && (
            <button
              onClick={() => handleCancel(consultation.id)}
              disabled={isBusy}
              className="btn-ghost btn-sm text-slate-500"
            >
              Cancel
            </button>
          )}
        </div>
      </div>
    )
  }

  if (compact) {
    if (loading || visible.length === 0) return null
    return (
      <div className="card">
        <div className="section-header">
          <h3 className="font-semibold text-slate-800">Video Consultations</h3>
          <button
            onClick={() => navigate(sectionPath)}
            className="text-xs text-blue-600 hover:underline"
          >
            View all
          </button>
        </div>
        <div className="flex flex-col gap-2">{visible.map(renderCard)}</div>
        {error && <p className="text-xs text-red-600 mt-3">{error}</p>}
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-5">
      {role === 'doctor' && (
        <div className="card">
          <div className="section-header">
            <div>
              <h3 className="font-semibold text-slate-800">Start a video consultation</h3>
              <p className="text-xs text-slate-500 mt-1">
                Choose an accepted patient. The LiveKit room opens only when you join.
              </p>
            </div>
          </div>

          {patients.length === 0 ? (
            <div className="alert-info">
              <Icon name="users" className="w-5 h-5" />
              <p>Accept a patient connection request before starting a video consultation.</p>
            </div>
          ) : (
            <div className="flex flex-col gap-3">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <div className="form-group">
                  <label className="form-label" htmlFor="consultation-patient">Patient</label>
                  <select
                    id="consultation-patient"
                    className="form-select"
                    value={patientId}
                    onChange={event => setPatientId(event.target.value)}
                  >
                    {patients.map(patient => (
                      <option key={patient.user_id} value={patient.user_id}>
                        {patient.full_name}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="form-group">
                  <label className="form-label" htmlFor="consultation-time">
                    Schedule for later <span className="font-normal text-slate-400">(optional)</span>
                  </label>
                  <input
                    id="consultation-time"
                    type="datetime-local"
                    className="form-input"
                    min={minDateTime}
                    value={scheduledAt}
                    onChange={event => setScheduledAt(event.target.value)}
                  />
                </div>
              </div>
              <div className="flex gap-2 flex-wrap">
                <button
                  onClick={handleStartNow}
                  disabled={creating !== null}
                  className="btn-primary"
                >
                  {creating === 'start'
                    ? <LoadingSpinner size="sm" />
                    : <Icon name="video" className="w-4 h-4" />}
                  Start now
                </button>
                <button
                  onClick={handleSchedule}
                  disabled={creating !== null || !scheduledAt}
                  className="btn-secondary"
                >
                  {creating === 'schedule'
                    ? <LoadingSpinner size="sm" />
                    : <Icon name="calendar" className="w-4 h-4" />}
                  Schedule
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      <div className="card">
        <div className="section-header">
          <div>
            <h3 className="font-semibold text-slate-800">My video consultations</h3>
            <p className="text-xs text-slate-500 mt-1">
              {role === 'patient'
                ? 'Join when your doctor has started the consultation.'
                : 'Scheduled, active, and past consultations.'}
            </p>
          </div>
          <button
            onClick={load}
            className="btn-ghost btn-sm"
            title="Refresh consultations"
          >
            <Icon name="refresh" className="w-4 h-4" />
            Refresh
          </button>
        </div>

        {error && (
          <div className="alert-error mb-3">
            <Icon name="alert" className="w-5 h-5" />
            <p>{error}</p>
          </div>
        )}
        {notice && (
          <div className="alert-success mb-3">
            <Icon name="checkCircle" className="w-5 h-5" />
            <p>{notice}</p>
          </div>
        )}

        {loading ? (
          <div className="flex justify-center py-10">
            <LoadingSpinner label="Loading consultations…" />
          </div>
        ) : visible.length === 0 ? (
          <div className="text-center py-10 text-slate-400">
            <span className="mx-auto mb-3 w-12 h-12 rounded-full bg-blue-50 text-blue-600 flex items-center justify-center">
              <Icon name="video" className="w-6 h-6" />
            </span>
            <p className="font-medium text-slate-600">No video consultations yet</p>
            <p className="text-sm mt-1">
              {role === 'doctor'
                ? 'Start one above with a connected patient.'
                : 'Your doctor can start a consultation from their dashboard.'}
            </p>
          </div>
        ) : (
          <div className="flex flex-col gap-2">{visible.map(renderCard)}</div>
        )}
      </div>

      <div className="alert-info">
        <Icon name="shield" className="w-5 h-5" />
        <p>
          Video consultations are encrypted by LiveKit and can only be joined by the
          connected doctor and patient. Camera and microphone access is requested when
          you enter the room.
        </p>
      </div>
    </div>
  )
}

export default VideoConsultations
