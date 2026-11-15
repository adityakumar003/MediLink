/** src/types/video.types.ts */
export type ConsultationStatus =
  | 'scheduled'
  | 'started'
  | 'in_progress'
  | 'completed'
  | 'cancelled'

export type VideoRole = 'patient' | 'doctor'

export interface Consultation {
  id: string
  room_name: string
  status: ConsultationStatus
  patient_user_id: string
  patient_name: string
  doctor_user_id: string
  doctor_name: string
  doctor_specialization?: string | null
  scheduled_at?: string | null
  started_at?: string | null
  ended_at?: string | null
  created_at: string
  role: VideoRole
  other_participant_id: string
  other_participant_name: string
  other_participant_role: VideoRole
  can_start: boolean
  can_join: boolean
  can_end: boolean
  can_cancel: boolean
}

export interface VideoTokenResponse {
  token: string
  server_url: string
  room_name: string
  role: VideoRole
  participant_name: string
  other_participant_name: string
  other_participant_role: VideoRole
  consultation: Consultation
}
