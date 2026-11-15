/**
 * src/components/patient/DoctorSearch.tsx
 * Search doctor by ID and discover nearby doctors.
 */
import { useState, type FC } from 'react'
import { getNearbyDoctors, searchDoctor } from '../../services/doctorService'
import { sendDoctorRequest } from '../../services/patientService'
import type { DoctorSearchResult, NearbyDoctorResult } from '../../types/doctor.types'
import LoadingSpinner from '../common/LoadingSpinner'
import Icon from '../common/Icon'

const RADII = [5, 10, 25, 50]

const DoctorSearch: FC = () => {
  const [doctorId, setDoctorId] = useState('')
  const [result, setResult] = useState<DoctorSearchResult | null>(null)
  const [nearbyDoctors, setNearbyDoctors] = useState<NearbyDoctorResult[]>([])
  const [searching, setSearching] = useState(false)
  const [locating, setLocating] = useState(false)
  const [hasSearchedNearby, setHasSearchedNearby] = useState(false)
  const [sendingDoctorId, setSendingDoctorId] = useState<string | null>(null)
  const [radiusKm, setRadiusKm] = useState(10)
  const [searchError, setSearchError] = useState('')
  const [successMsg, setSuccessMsg] = useState('')

  const handleSearch = async () => {
    if (!doctorId.trim()) return
    setSearching(true)
    setSearchError('')
    setResult(null)
    setSuccessMsg('')
    try {
      const data = await searchDoctor(doctorId.trim().toUpperCase())
      setResult(data)
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setSearchError(msg || 'Doctor not found.')
    } finally {
      setSearching(false)
    }
  }

  const handleFindNearby = () => {
    setSearchError('')
    setSuccessMsg('')
    setNearbyDoctors([])

    if (!('geolocation' in navigator)) {
      setSearchError('Location services are not available in this browser.')
      return
    }

    setLocating(true)
    navigator.geolocation.getCurrentPosition(
      async position => {
        try {
          const { latitude, longitude } = position.coords
          const doctors = await getNearbyDoctors(latitude, longitude, radiusKm)
          setNearbyDoctors(doctors)
          setHasSearchedNearby(true)
          if (doctors.length === 0) {
            setSearchError('No doctors with saved practice locations were found in this radius.')
          }
        } catch {
          setSearchError('Unable to find nearby doctors right now.')
        } finally {
          setLocating(false)
        }
      },
      () => {
        setSearchError('Allow location access to find nearby doctors.')
        setLocating(false)
      },
      { enableHighAccuracy: true, timeout: 10000 },
    )
  }

  const handleSendRequest = async (doctor: Pick<DoctorSearchResult, 'doctor_id'>) => {
    setSendingDoctorId(doctor.doctor_id)
    setSuccessMsg('')
    setSearchError('')
    try {
      const res = await sendDoctorRequest(doctor.doctor_id)
      setSuccessMsg(res.message)
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setSearchError(msg || 'Failed to send request.')
    } finally {
      setSendingDoctorId(null)
    }
  }

  return (
    <div className="flex flex-col gap-5">
      {/* ID search */}
      <div className="card">
        <h3 className="font-semibold text-slate-900 text-lg mb-4">Search by Doctor ID</h3>
        <div className="flex gap-2">
          <input
            type="text"
            className="form-input flex-1"
            placeholder="e.g. DR-ABC123"
            value={doctorId}
            onChange={e => setDoctorId(e.target.value.toUpperCase())}
            onKeyDown={e => e.key === 'Enter' && handleSearch()}
          />
          <button onClick={handleSearch} disabled={searching || !doctorId.trim()} className="btn-primary shrink-0">
            {searching ? <LoadingSpinner size="sm" /> : (<><Icon name="search" className="w-4 h-4" /> Search</>)}
          </button>
        </div>

        {result && (
          <div className="mt-4 border border-slate-200/70 rounded-2xl p-4 bg-white/60">
            <div className="flex items-start justify-between gap-3">
              <div className="flex items-center gap-3 min-w-0">
                <span className="avatar w-10 h-10 text-sm">
                  {result.full_name.charAt(0).toUpperCase()}
                </span>
                <div className="min-w-0">
                  <p className="font-semibold text-slate-800 truncate">{result.full_name}</p>
                  <p className="text-xs text-blue-600 font-mono">{result.doctor_id}</p>
                  <div className="mt-1.5 flex flex-wrap gap-2 text-xs text-slate-600">
                    <span className="badge bg-blue-50 text-blue-700">{result.specialization}</span>
                    {result.experience > 0 && <span>{result.experience} yrs exp.</span>}
                    {result.hospital && (
                      <span className="inline-flex items-center gap-1">
                        <Icon name="mapPin" className="w-3 h-3" />{result.hospital}
                      </span>
                    )}
                  </div>
                </div>
              </div>
              <button
                onClick={() => handleSendRequest(result)}
                disabled={sendingDoctorId === result.doctor_id}
                className="btn-primary btn-sm shrink-0"
              >
                {sendingDoctorId === result.doctor_id ? <LoadingSpinner size="sm" /> : 'Send Request'}
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Nearby */}
      <div>
        <div className="flex items-center justify-between gap-3 flex-wrap mb-3">
          <h3 className="font-semibold text-slate-900 text-lg">Nearby doctors</h3>
          <div className="flex items-center gap-2">
            <div className="radius-pills">
              {RADII.map(r => (
                <button
                  key={r}
                  onClick={() => setRadiusKm(r)}
                  className={`radius-pill ${radiusKm === r ? 'active' : ''}`}
                >
                  {r} km
                </button>
              ))}
            </div>
            <button onClick={handleFindNearby} disabled={locating} className="btn-secondary btn-sm shrink-0">
              {locating ? <LoadingSpinner size="sm" /> : (<><Icon name="navigation" className="w-3.5 h-3.5" /> Use GPS</>)}
            </button>
          </div>
        </div>

        {searchError && <div className="alert-error mb-3">{searchError}</div>}
        {successMsg && <div className="alert-success mb-3">{successMsg}</div>}

        {nearbyDoctors.length > 0 ? (
          <div className="card !p-3 flex flex-col gap-1">
            {nearbyDoctors.map(doctor => (
              <div key={doctor.user_id} className="history-row !cursor-default">
                <span className="avatar w-10 h-10 text-sm">
                  {doctor.full_name.charAt(0).toUpperCase()}
                </span>
                <div className="flex-1 min-w-0">
                  <p className="font-semibold text-slate-800 text-sm truncate">{doctor.full_name}</p>
                  <p className="text-xs text-blue-600 font-mono">{doctor.doctor_id} · {doctor.distance_km} km away</p>
                  <p className="text-xs text-slate-500 truncate">{doctor.specialization}{doctor.hospital ? ` · ${doctor.hospital}` : ''}</p>
                </div>
                <button
                  onClick={() => handleSendRequest(doctor)}
                  disabled={sendingDoctorId === doctor.doctor_id}
                  className="btn-primary btn-sm shrink-0"
                >
                  {sendingDoctorId === doctor.doctor_id ? <LoadingSpinner size="sm" /> : 'Connect'}
                </button>
              </div>
            ))}
          </div>
        ) : !hasSearchedNearby && !searchError ? (
          <div className="card text-center py-14">
            <span className="mx-auto mb-4 w-14 h-14 rounded-full bg-blue-50 text-blue-600 flex items-center justify-center">
              <Icon name="inbox" className="w-6 h-6" />
            </span>
            <p className="font-semibold text-slate-800">Share your location</p>
            <p className="text-sm text-slate-500 mt-1">Use GPS to see doctors within your selected radius.</p>
          </div>
        ) : null}
      </div>
    </div>
  )
}

export default DoctorSearch
