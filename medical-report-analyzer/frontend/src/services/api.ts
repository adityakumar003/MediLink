/**
 * src/services/api.ts
 * Axios instance with JWT interceptor and 401 auto-logout.
 */
import axios from 'axios'

// Empty by default: Vite's dev proxy routes same-origin API calls to the
// backend. Deployments with a separate API origin can set VITE_API_URL.
const configuredBaseUrl = (
  import.meta.env.VITE_API_URL
  || import.meta.env.VITE_API_BASE_URL
  || ''
).trim().replace(/\/+$/, '')

const api = axios.create({
  baseURL: configuredBaseUrl,
  timeout: 300000,      // 5 minutes — hosted model cold start / queue can take a while
  headers: { 'Content-Type': 'application/json' },
})

// Attach JWT token to every request
api.interceptors.request.use(config => {
  const token = localStorage.getItem('medreport_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// On 401 → clear storage and redirect to login
api.interceptors.response.use(
  response => response,
  error => {
    if (error.response?.status === 401) {
      localStorage.removeItem('medreport_token')
      localStorage.removeItem('medreport_user')
      if (!window.location.pathname.includes('/login')) {
        window.location.href = '/login'
      }
    }
    return Promise.reject(error)
  }
)

export default api
