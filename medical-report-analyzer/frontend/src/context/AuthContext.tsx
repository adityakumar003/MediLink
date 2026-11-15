/**
 * src/context/AuthContext.tsx
 * Global auth state: user info + JWT token management.
 */
import { createContext, useState, useEffect, type FC, type ReactNode } from 'react'
import type { AuthUser, AuthContextType } from '../types/auth.types'

export const AuthContext = createContext<AuthContextType>({
  user: null,
  token: null,
  isAuthenticated: false,
  isLoading: true,
  login: () => {},
  logout: () => {},
})

const TOKEN_KEY = 'medreport_token'
const USER_KEY  = 'medreport_user'

export const AuthProvider: FC<{ children: ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<AuthUser | null>(null)
  const [token, setToken] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(true)

  useEffect(() => {
    const applyStoredSession = () => {
      try {
        const storedToken = localStorage.getItem(TOKEN_KEY)
        const storedUser  = localStorage.getItem(USER_KEY)
        if (storedToken && storedUser) {
          setToken(storedToken)
          setUser(JSON.parse(storedUser))
        } else {
          setToken(null)
          setUser(null)
        }
      } catch {
        localStorage.removeItem(TOKEN_KEY)
        localStorage.removeItem(USER_KEY)
        setToken(null)
        setUser(null)
      }
    }

    // Restore from localStorage on mount.
    applyStoredSession()
    setIsLoading(false)

    // localStorage is shared by every tab in the same browser profile. When a
    // different account signs in or out in another tab, update this tab too.
    // Without this, a doctor dashboard could keep rendering after the shared
    // token was replaced by a patient login, causing misleading 403 errors.
    const handleStorage = (event: StorageEvent) => {
      if (event.key !== null && event.key !== TOKEN_KEY && event.key !== USER_KEY) return
      applyStoredSession()
    }
    window.addEventListener('storage', handleStorage)
    return () => window.removeEventListener('storage', handleStorage)
  }, [])

  const login = (newToken: string, newUser: AuthUser) => {
    localStorage.setItem(TOKEN_KEY, newToken)
    localStorage.setItem(USER_KEY, JSON.stringify(newUser))
    setToken(newToken)
    setUser(newUser)
  }

  const logout = () => {
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(USER_KEY)
    setToken(null)
    setUser(null)
  }

  return (
    <AuthContext.Provider value={{
      user, token,
      isAuthenticated: !!token && !!user,
      isLoading,
      login, logout,
    }}>
      {children}
    </AuthContext.Provider>
  )
}
