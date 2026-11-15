/**
 * src/pages/video/VideoCallPage.tsx
 * LiveKit-powered 1:1 video consultation room.
 */
import { useCallback, useEffect, useRef, useState, type FC } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import {
  LiveKitRoom,
  RoomAudioRenderer,
  StartAudio,
  VideoTrack,
  isTrackReference,
  useConnectionState,
  useLocalParticipant,
  useRemoteParticipants,
  useRoomContext,
  useTracks,
} from '@livekit/components-react'
import {
  ConnectionState,
  RoomEvent,
  Track,
  type Room,
} from 'livekit-client'
import '@livekit/components-styles'
import { useAuth } from '../../hooks/useAuth'
import Icon from '../../components/common/Icon'
import LoadingSpinner from '../../components/common/LoadingSpinner'
import {
  endConsultation,
  getConsultation,
  getVideoToken,
  leaveConsultation,
} from '../../services/videoService'
import type { VideoTokenResponse } from '../../types/video.types'

const END_CALL_MESSAGE = JSON.stringify({ type: 'consultation_ended' })
const encoder = new TextEncoder()

function apiErrorMessage(err: unknown, fallback: string): string {
  const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
  return typeof detail === 'string' && detail.trim() ? detail : fallback
}

function initials(name: string): string {
  return name.split(' ').map(part => part.charAt(0)).slice(0, 2).join('').toUpperCase() || '?'
}

function doctorName(name: string): string {
  return name.toLowerCase().startsWith('dr.') ? name : `Dr. ${name}`
}

function connectionLabel(state: ConnectionState): string {
  switch (state) {
    case ConnectionState.Connected:
      return 'Connected'
    case ConnectionState.Connecting:
      return 'Connecting'
    case ConnectionState.Reconnecting:
    case ConnectionState.SignalReconnecting:
      return 'Reconnecting'
    default:
      return 'Disconnected'
  }
}

function connectionDotClass(state: ConnectionState): string {
  if (state === ConnectionState.Connected) return 'bg-emerald-400'
  if (state === ConnectionState.Reconnecting || state === ConnectionState.SignalReconnecting) {
    return 'bg-amber-400'
  }
  if (state === ConnectionState.Connecting) return 'bg-blue-400'
  return 'bg-slate-500'
}

const ControlButton: FC<{
  label: string
  icon: 'mic' | 'micOff' | 'camera' | 'cameraOff' | 'phoneOff'
  onClick: () => void
  disabled?: boolean
  off?: boolean
  danger?: boolean
}> = ({ label, icon, onClick, disabled = false, off = false, danger = false }) => (
  <button
    type="button"
    onClick={onClick}
    disabled={disabled}
    aria-label={label}
    title={label}
    className={`w-12 h-12 sm:w-14 sm:h-14 rounded-full flex items-center justify-center transition-colors
      disabled:opacity-50 disabled:cursor-not-allowed ${
      danger
        ? 'bg-red-500 hover:bg-red-600 text-white'
        : off
          ? 'bg-red-500/90 hover:bg-red-500 text-white'
          : 'bg-slate-700 hover:bg-slate-600 text-white'
    }`}
  >
    {disabled
      ? <LoadingSpinner size="sm" />
      : <Icon name={icon} className="w-5 h-5 sm:w-6 sm:h-6" />}
  </button>
)

interface CallStageProps {
  session: VideoTokenResponse
  onLeave: (room: Room) => Promise<void>
  onRemoteEnded: () => void
  leaving: boolean
  actionError: string
  mediaWarning: string
}

const CallStage: FC<CallStageProps> = ({
  session,
  onLeave,
  onRemoteEnded,
  leaving,
  actionError,
  mediaWarning,
}) => {
  const room = useRoomContext()
  const connectionState = useConnectionState(room)
  const remoteParticipants = useRemoteParticipants({ room })
  const {
    localParticipant,
    isMicrophoneEnabled,
    isCameraEnabled,
    lastMicrophoneError,
    lastCameraError,
  } = useLocalParticipant({ room })
  const cameraTracks = useTracks(
    [{ source: Track.Source.Camera, withPlaceholder: true }],
    { room },
  )
  const [controlError, setControlError] = useState('')
  const [togglingMicrophone, setTogglingMicrophone] = useState(false)
  const [togglingCamera, setTogglingCamera] = useState(false)

  const remote = remoteParticipants[0]
  const localCameraTrack = cameraTracks.find(
    track => track.participant.identity === localParticipant.identity,
  )
  const remoteCameraTrack = remote
    ? cameraTracks.find(track => track.participant.identity === remote.identity)
    : undefined
  const localVideoRef = localCameraTrack
    && isTrackReference(localCameraTrack)
    && !localCameraTrack.publication.isMuted
    ? localCameraTrack
    : null
  const remoteVideoRef = remoteCameraTrack
    && isTrackReference(remoteCameraTrack)
    && !remoteCameraTrack.publication.isMuted
    ? remoteCameraTrack
    : null

  const otherDisplayName = session.other_participant_role === 'doctor'
    ? doctorName(session.other_participant_name)
    : session.other_participant_name
  const ownDisplayName = session.role === 'doctor'
    ? doctorName(session.participant_name)
    : session.participant_name
  const deviceError = mediaWarning
    || (lastMicrophoneError ? 'Microphone access failed. Check browser permissions and try again.' : '')
    || (lastCameraError ? 'Camera access failed. Check browser permissions and try again.' : '')

  useEffect(() => {
    const handleData = (payload: Uint8Array) => {
      try {
        const message = JSON.parse(new TextDecoder().decode(payload)) as { type?: string }
        if (message.type === 'consultation_ended' && session.role === 'patient') {
          onRemoteEnded()
        }
      } catch {
        // Ignore unrelated or malformed data packets.
      }
    }
    room.on(RoomEvent.DataReceived, handleData)
    return () => { room.off(RoomEvent.DataReceived, handleData) }
  }, [room, onRemoteEnded, session.role])

  const toggleMicrophone = async () => {
    setControlError('')
    setTogglingMicrophone(true)
    try {
      await localParticipant.setMicrophoneEnabled(!isMicrophoneEnabled)
    } catch {
      setControlError('Could not change the microphone. Check browser permissions.')
    } finally {
      setTogglingMicrophone(false)
    }
  }

  const toggleCamera = async () => {
    setControlError('')
    setTogglingCamera(true)
    try {
      await localParticipant.setCameraEnabled(!isCameraEnabled)
    } catch {
      setControlError('Could not change the camera. Check browser permissions.')
    } finally {
      setTogglingCamera(false)
    }
  }

  const handleLeaveClick = () => {
    const prompt = session.role === 'doctor'
      ? 'End this consultation for both participants?'
      : 'Leave this video consultation?'
    if (window.confirm(prompt)) {
      void onLeave(room)
    }
  }

  return (
    <div className="min-h-screen bg-slate-950 text-white flex flex-col gap-3 p-3 sm:p-5">
      <RoomAudioRenderer room={room} />

      <header className="w-full max-w-6xl mx-auto flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-3 min-w-0">
          <span className="w-10 h-10 rounded-full bg-blue-600 flex items-center justify-center shrink-0">
            <Icon name="video" className="w-5 h-5" />
          </span>
          <div className="min-w-0">
            <p className="text-sm sm:text-base font-semibold truncate">
              {session.role === 'doctor'
                ? `Consultation with ${session.other_participant_name}`
                : `Consultation with ${doctorName(session.other_participant_name)}`}
            </p>
            <p className="text-xs text-slate-400 truncate">
              {session.other_participant_role === 'doctor'
                ? (session.consultation.doctor_specialization || 'Doctor')
                : 'Patient'}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <span className="inline-flex items-center gap-2 rounded-full bg-white/10 border border-white/10 px-3 py-1.5 text-xs text-slate-200">
            <span className={`w-2 h-2 rounded-full ${connectionDotClass(connectionState)}`} />
            {connectionLabel(connectionState)}
          </span>
          <span className="hidden sm:inline-flex badge bg-white/10 text-slate-200 border border-white/10">
            <Icon name="shield" className="w-3.5 h-3.5 mr-1" />
            Secure video
          </span>
        </div>
      </header>

      <main className="w-full max-w-6xl mx-auto flex-1 min-h-0 flex flex-col gap-3">
        {(deviceError || controlError || actionError) && (
          <div className="rounded-2xl border border-amber-400/30 bg-amber-400/10 px-4 py-3 text-sm text-amber-100 flex items-start gap-2">
            <Icon name="alert" className="w-5 h-5 shrink-0" />
            <p>{controlError || actionError || deviceError}</p>
          </div>
        )}

        <div className="relative flex-1 min-h-[48vh] rounded-3xl overflow-hidden bg-gradient-to-br from-slate-900 via-slate-900 to-slate-800 border border-white/10">
          {remote && remoteVideoRef ? (
            <VideoTrack
              trackRef={remoteVideoRef}
              className="absolute inset-0 w-full h-full object-cover"
            />
          ) : (
            <div className="absolute inset-0 flex flex-col items-center justify-center px-6 text-center">
              <span className="w-20 h-20 sm:w-24 sm:h-24 rounded-full bg-blue-500/20 border border-blue-300/20 text-blue-100 flex items-center justify-center text-2xl sm:text-3xl font-bold">
                {initials(otherDisplayName)}
              </span>
              <h2 className="mt-5 text-xl sm:text-2xl font-semibold text-white">
                {remote ? otherDisplayName : `Waiting for ${otherDisplayName}`}
              </h2>
              <p className="mt-2 max-w-md text-sm text-slate-400">
                {remote
                  ? (remote.isCameraEnabled ? 'Connecting video…' : 'Camera is off')
                  : 'You are in the consultation room. Keep this tab open and the other participant will join shortly.'}
              </p>
            </div>
          )}

          <div className="absolute top-3 left-3 flex items-center gap-2 flex-wrap">
            <span className="rounded-full bg-black/45 backdrop-blur px-3 py-1.5 text-xs font-medium text-white">
              {remote ? otherDisplayName : `Waiting for ${otherDisplayName}`}
            </span>
            <span className="rounded-full bg-black/30 backdrop-blur px-2.5 py-1.5 text-[11px] text-slate-300 capitalize">
              {session.other_participant_role}
            </span>
          </div>

          {localVideoRef ? (
            <div className="absolute right-3 bottom-3 w-28 sm:w-48 aspect-video rounded-2xl overflow-hidden border-2 border-white/20 bg-slate-800 shadow-xl">
              <VideoTrack
                trackRef={localVideoRef}
                className="w-full h-full object-cover scale-x-[-1]"
              />
            </div>
          ) : (
            <div className="absolute right-3 bottom-3 w-28 sm:w-48 aspect-video rounded-2xl overflow-hidden border-2 border-white/20 bg-slate-800 shadow-xl flex flex-col items-center justify-center text-slate-300">
              <span className="avatar w-9 h-9 text-xs">{initials(ownDisplayName)}</span>
              <span className="text-[10px] mt-1">Camera off</span>
            </div>
          )}

          {leaving && (
            <div className="absolute inset-0 bg-slate-950/80 backdrop-blur-sm flex items-center justify-center">
              <LoadingSpinner size="lg" label="Leaving consultation…" />
            </div>
          )}
        </div>

        <div className="rounded-3xl border border-white/10 bg-slate-900/80 px-3 py-3 sm:px-5 flex items-center justify-center gap-3 sm:gap-4 flex-wrap">
          <div className="flex flex-col items-center gap-1">
            <ControlButton
              label={isMicrophoneEnabled ? 'Mute microphone' : 'Unmute microphone'}
              icon={isMicrophoneEnabled ? 'mic' : 'micOff'}
              onClick={() => { void toggleMicrophone() }}
              disabled={togglingMicrophone || leaving}
              off={!isMicrophoneEnabled}
            />
            <span className="text-[10px] text-slate-400">Microphone</span>
          </div>
          <div className="flex flex-col items-center gap-1">
            <ControlButton
              label={isCameraEnabled ? 'Turn camera off' : 'Turn camera on'}
              icon={isCameraEnabled ? 'camera' : 'cameraOff'}
              onClick={() => { void toggleCamera() }}
              disabled={togglingCamera || leaving}
              off={!isCameraEnabled}
            />
            <span className="text-[10px] text-slate-400">Camera</span>
          </div>
          <div className="flex flex-col items-center gap-1">
            <ControlButton
              label={session.role === 'doctor' ? 'End consultation' : 'Leave consultation'}
              icon="phoneOff"
              onClick={handleLeaveClick}
              disabled={leaving}
              danger
            />
            <span className="text-[10px] text-slate-400">
              {session.role === 'doctor' ? 'End' : 'Leave'}
            </span>
          </div>
          <StartAudio
            label="Enable audio"
            className="rounded-full bg-blue-600 hover:bg-blue-500 px-4 py-2 text-sm font-medium text-white"
          />
        </div>
      </main>
    </div>
  )
}

const VideoCallPage: FC = () => {
  const { consultationId } = useParams<{ consultationId: string }>()
  const { user } = useAuth()
  const navigate = useNavigate()
  const [session, setSession] = useState<VideoTokenResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [roomError, setRoomError] = useState('')
  const [mediaWarning, setMediaWarning] = useState('')
  const [actionError, setActionError] = useState('')
  const [leaving, setLeaving] = useState(false)
  const [connectionLost, setConnectionLost] = useState(false)
  const [reconnecting, setReconnecting] = useState(false)
  const [roomKey, setRoomKey] = useState(0)
  const intentionalLeave = useRef(false)

  const backPath = user?.role === 'doctor' ? '/doctor/consultations' : '/patient/consultations'

  const loadToken = useCallback(async () => {
    if (!consultationId) {
      setError('Missing consultation identifier.')
      setLoading(false)
      return
    }
    setError('')
    setRoomError('')
    try {
      const response = await getVideoToken(consultationId)
      setSession(response)
    } catch (err) {
      setError(apiErrorMessage(err, 'Could not prepare the video consultation.'))
    } finally {
      setLoading(false)
    }
  }, [consultationId])

  useEffect(() => {
    void loadToken()
  }, [loadToken])

  // Data messages normally close the patient's room immediately when the
  // doctor ends the call. This lightweight poll also covers a lost data
  // packet or a consultation cancelled from another tab.
  useEffect(() => {
    if (!session || !consultationId) return
    let cancelled = false
    const checkStatus = async () => {
      try {
        const latest = await getConsultation(consultationId)
        if (!cancelled && (latest.status === 'completed' || latest.status === 'cancelled')) {
          intentionalLeave.current = true
          navigate(backPath, { replace: true })
        }
      } catch {
        // Keep the media connection alive through transient API failures.
      }
    }
    const timer = window.setInterval(checkStatus, 15000)
    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [backPath, consultationId, navigate, session])

  const handleLeave = useCallback(async (room: Room) => {
    if (!session) return
    setLeaving(true)
    setActionError('')
    try {
      if (session.role === 'doctor') {
        await endConsultation(session.consultation.id)
        // Tell the patient the doctor ended the call, so their UI does not
        // mistake the disconnect for a temporary network problem.
        try {
          await room.localParticipant.publishData(encoder.encode(END_CALL_MESSAGE), {
            reliable: true,
          })
        } catch {
          // The backend status is already completed; this notification is best-effort.
        }
      } else {
        await leaveConsultation(session.consultation.id)
      }
      intentionalLeave.current = true
      await room.disconnect()
      navigate(backPath, { replace: true })
    } catch (err) {
      setActionError(apiErrorMessage(err, 'Could not leave the consultation. Please retry.'))
      setLeaving(false)
    }
  }, [backPath, navigate, session])

  const handleRemoteEnded = useCallback(() => {
    intentionalLeave.current = true
    navigate(backPath, { replace: true })
  }, [backPath, navigate])

  const handleReconnect = async () => {
    if (!consultationId) return
    setReconnecting(true)
    setRoomError('')
    try {
      const response = await getVideoToken(consultationId)
      setSession(response)
      setConnectionLost(false)
      setRoomKey(key => key + 1)
    } catch (err) {
      setConnectionLost(false)
      setRoomError(apiErrorMessage(err, 'Could not reconnect to the consultation.'))
    } finally {
      setReconnecting(false)
    }
  }

  const retryInitialLoad = async () => {
    setLoading(true)
    setSession(null)
    await loadToken()
  }

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center p-6">
        <div className="card max-w-md w-full text-center">
          <LoadingSpinner size="lg" label="Preparing your secure video consultation…" />
        </div>
      </div>
    )
  }

  if (error || !session) {
    return (
      <div className="min-h-screen flex items-center justify-center p-6">
        <div className="card max-w-lg w-full text-center">
          <span className="mx-auto mb-4 w-14 h-14 rounded-full bg-red-50 text-red-600 flex items-center justify-center">
            <Icon name="alert" className="w-7 h-7" />
          </span>
          <h1 className="text-xl font-bold text-slate-900">Video consultation unavailable</h1>
          <p className="text-sm text-slate-500 mt-2">
            {error || 'The consultation could not be loaded.'}
          </p>
          <div className="flex items-center justify-center gap-2 mt-5 flex-wrap">
            <button onClick={retryInitialLoad} className="btn-primary">
              <Icon name="refresh" className="w-4 h-4" /> Try again
            </button>
            <button onClick={() => navigate(backPath)} className="btn-secondary">
              Back to dashboard
            </button>
          </div>
        </div>
      </div>
    )
  }

  if (roomError) {
    return (
      <div className="min-h-screen flex items-center justify-center p-6">
        <div className="card max-w-lg w-full text-center">
          <span className="mx-auto mb-4 w-14 h-14 rounded-full bg-red-50 text-red-600 flex items-center justify-center">
            <Icon name="alert" className="w-7 h-7" />
          </span>
          <h1 className="text-xl font-bold text-slate-900">Could not connect to the room</h1>
          <p className="text-sm text-slate-500 mt-2">{roomError}</p>
          <div className="flex items-center justify-center gap-2 mt-5 flex-wrap">
            <button onClick={handleReconnect} className="btn-primary">
              <Icon name="refresh" className="w-4 h-4" /> Rejoin
            </button>
            <button onClick={() => navigate(backPath)} className="btn-secondary">
              Back to dashboard
            </button>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="relative">
      <LiveKitRoom
        key={roomKey}
        token={session.token}
        serverUrl={session.server_url}
        connect
        audio
        video
        onConnected={() => setConnectionLost(false)}
        onDisconnected={() => {
          if (!intentionalLeave.current) setConnectionLost(true)
        }}
        onError={err => {
          setRoomError(err.message || 'The video room connection failed.')
        }}
        onMediaDeviceFailure={(_failure, kind?: MediaDeviceKind) => {
          setMediaWarning(
            kind === 'audioinput'
              ? 'Microphone access was blocked. Allow microphone access in your browser and try again.'
              : 'Camera access was blocked. Allow camera access in your browser and try again.',
          )
        }}
      >
        <CallStage
          session={session}
          onLeave={handleLeave}
          onRemoteEnded={handleRemoteEnded}
          leaving={leaving}
          actionError={actionError}
          mediaWarning={mediaWarning}
        />
      </LiveKitRoom>

      {connectionLost && (
        <div className="fixed inset-0 z-50 bg-slate-950/80 backdrop-blur-sm flex items-center justify-center p-6">
          <div className="card max-w-md w-full text-center">
            <span className="mx-auto mb-4 w-14 h-14 rounded-full bg-amber-50 text-amber-600 flex items-center justify-center">
              <Icon name="refresh" className="w-7 h-7" />
            </span>
            <h2 className="text-xl font-bold text-slate-900">Connection lost</h2>
            <p className="text-sm text-slate-500 mt-2">
              LiveKit will try to reconnect automatically. Rejoin if the connection does not recover.
            </p>
            <div className="flex items-center justify-center gap-2 mt-5 flex-wrap">
              <button onClick={handleReconnect} disabled={reconnecting} className="btn-primary">
                {reconnecting ? <LoadingSpinner size="sm" /> : <Icon name="refresh" className="w-4 h-4" />}
                Rejoin
              </button>
              <button onClick={() => navigate(backPath)} className="btn-secondary">
                Back to dashboard
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default VideoCallPage
