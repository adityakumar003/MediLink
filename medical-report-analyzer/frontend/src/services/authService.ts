/**
 * src/services/authService.ts
 * Handles authentication API calls.
 */
import api from './api'
import type { LoginRequest, RegisterRequest, TokenResponse } from '../types/auth.types'

export async function login(payload: LoginRequest): Promise<TokenResponse> {
  const res = await api.post<TokenResponse>('/auth/login', payload)
  return res.data
}

export async function register(payload: RegisterRequest): Promise<TokenResponse> {
  const res = await api.post<TokenResponse>('/auth/register', payload)
  return res.data
}

export async function logout(): Promise<void> {
  await api.post('/auth/logout')
}

export async function getMe(): Promise<TokenResponse['user']> {
  const res = await api.get<TokenResponse['user']>('/auth/me')
  return res.data
}

export async function uploadProfilePhoto(file: File): Promise<{ has_photo: boolean }> {
  const formData = new FormData()
  formData.append('file', file)
  const res = await api.post('/auth/profile-photo', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return res.data
}

export async function fetchMyPhoto(): Promise<string | null> {
  try {
    const res = await api.get<Blob>('/auth/me/photo', { responseType: 'blob' })
    return URL.createObjectURL(res.data)
  } catch {
    return null
  }
}

export async function deleteProfilePhoto(): Promise<void> {
  await api.delete('/auth/profile-photo')
}
