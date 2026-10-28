import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'
import { apiRequest, ApiError } from '../services/api'
import type { AuthResponse, AuthUser } from '../types/api'

interface AuthContextValue {
  user: AuthUser | null
  checkingSession: boolean
  login: (login: string, password: string) => Promise<void>
  logout: () => Promise<void>
  clearSession: () => void
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null)
  const [checkingSession, setCheckingSession] = useState(true)

  useEffect(() => {
    let current = true
    apiRequest<AuthResponse>('/api/auth/me')
      .then((response) => {
        if (current) setUser(response.user)
      })
      .catch((error: unknown) => {
        if (current && (!(error instanceof ApiError) || error.status !== 401)) {
          console.error('세션 확인에 실패했습니다.')
        }
      })
      .finally(() => {
        if (current) setCheckingSession(false)
      })
    return () => {
      current = false
    }
  }, [])

  const login = useCallback(async (loginId: string, password: string) => {
    const response = await apiRequest<AuthResponse>('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ login: loginId, password }),
    })
    setUser(response.user)
  }, [])

  const logout = useCallback(async () => {
    try {
      await apiRequest<{ success: boolean }>('/api/auth/logout', { method: 'POST' })
    } finally {
      setUser(null)
    }
  }, [])

  const clearSession = useCallback(() => setUser(null), [])
  const value = useMemo(
    () => ({ user, checkingSession, login, logout, clearSession }),
    [user, checkingSession, login, logout, clearSession],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth는 AuthProvider 안에서 사용해야 합니다.')
  return context
}
