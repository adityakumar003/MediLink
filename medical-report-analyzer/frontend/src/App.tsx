/**
 * src/App.tsx
 * Root application with React Router v6 routing.
 */
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider } from './context/AuthContext'
import ProtectedRoute from './components/common/ProtectedRoute'

// Auth pages
import LoginPage    from './pages/auth/LoginPage'
import RegisterPage from './pages/auth/RegisterPage'

// Dashboards
import PatientDashboard from './pages/patient/PatientDashboard'
import DoctorDashboard  from './pages/doctor/DoctorDashboard'

// 404
const NotFoundPage = () => (
  <div className="min-h-screen flex flex-col items-center justify-center gap-4">
    <p className="text-6xl">🏥</p>
    <h1 className="text-2xl font-bold text-slate-700">Page Not Found</h1>
    <a href="/login" className="btn-primary">Back to Login</a>
  </div>
)

function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          {/* Public */}
          <Route path="/login"    element={<LoginPage />} />
          <Route path="/register" element={<RegisterPage />} />

          {/* Patient routes */}
          <Route path="/patient/dashboard" element={
            <ProtectedRoute requiredRole="patient">
              <PatientDashboard section="overview" />
            </ProtectedRoute>
          } />
          <Route path="/patient/doctors" element={
            <ProtectedRoute requiredRole="patient">
              <PatientDashboard section="doctors" />
            </ProtectedRoute>
          } />
          <Route path="/patient/upload" element={
            <ProtectedRoute requiredRole="patient">
              <PatientDashboard section="upload" />
            </ProtectedRoute>
          } />
          <Route path="/patient/history" element={
            <ProtectedRoute requiredRole="patient">
              <PatientDashboard section="history" />
            </ProtectedRoute>
          } />
          <Route path="/patient/analytics" element={
            <ProtectedRoute requiredRole="patient">
              <PatientDashboard section="analytics" />
            </ProtectedRoute>
          } />
          <Route path="/patient/chats" element={
            <ProtectedRoute requiredRole="patient">
              <PatientDashboard section="chats" />
            </ProtectedRoute>
          } />

          {/* Doctor routes */}
          <Route path="/doctor/dashboard" element={
            <ProtectedRoute requiredRole="doctor">
              <DoctorDashboard section="overview" />
            </ProtectedRoute>
          } />
          <Route path="/doctor/requests" element={
            <ProtectedRoute requiredRole="doctor">
              <DoctorDashboard section="requests" />
            </ProtectedRoute>
          } />
          <Route path="/doctor/patients" element={
            <ProtectedRoute requiredRole="doctor">
              <DoctorDashboard section="patients" />
            </ProtectedRoute>
          } />
          <Route path="/doctor/analytics" element={
            <ProtectedRoute requiredRole="doctor">
              <DoctorDashboard section="analytics" />
            </ProtectedRoute>
          } />

          {/* Default redirect */}
          <Route path="/" element={<Navigate to="/login" replace />} />
          <Route path="*" element={<NotFoundPage />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  )
}

export default App
