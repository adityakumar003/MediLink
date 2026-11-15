/**
 * src/services/videoService.ts
 * LiveKit video consultation API calls.
 */
import api from './api'
import type { Consultation, VideoTokenResponse } from '../types/video.types'

export async function listConsultations(): Promise<Consultation[]> {
  const res = await api.get<Consultation[]>('/video/consultations')
  return res.data
}

export async function getConsultation(consultationId: string): Promise<Consultation> {
  const res = await api.get<Consultation>(`/video/consultations/${consultationId}`)
  return res.data
}

export async function startConsultation(patientId: string): Promise<Consultation> {
  const res = await api.post<Consultation>('/video/consultations', { patient_id: patientId })
  return res.data
}

export async function scheduleConsultation(
  patientId: string,
  scheduledAt: string,
): Promise<Consultation> {
  const res = await api.post<Consultation>('/video/consultations', {
    patient_id: patientId,
    scheduled_at: scheduledAt,
  })
  return res.data
}

export async function startScheduledConsultation(consultationId: string): Promise<Consultation> {
  const res = await api.post<Consultation>(`/video/consultations/${consultationId}/start`)
  return res.data
}

export async function getVideoToken(consultationId: string): Promise<VideoTokenResponse> {
  const res = await api.post<VideoTokenResponse>('/video/token', {
    consultation_id: consultationId,
  })
  return res.data
}

export async function leaveConsultation(consultationId: string): Promise<Consultation> {
  const res = await api.post<Consultation>(`/video/consultations/${consultationId}/leave`)
  return res.data
}

export async function endConsultation(consultationId: string): Promise<Consultation> {
  const res = await api.post<Consultation>(`/video/consultations/${consultationId}/end`)
  return res.data
}

export async function cancelConsultation(consultationId: string): Promise<Consultation> {
  const res = await api.post<Consultation>(`/video/consultations/${consultationId}/cancel`)
  return res.data
}
