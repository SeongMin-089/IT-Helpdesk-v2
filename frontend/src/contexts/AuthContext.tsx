import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react'
import { apiRequest, ApiError, setUnauthorizedHandler } from '../services/api'
import type { AuthResponse, AuthUser } from '../types/api'

interface AuthContextValue {
  user: AuthUser | null
  checkingSession: boolean
  sessionError: string
  login: (login: string, password: string) => Promise<void>
  logout: () => Promise<void>
  retrySession: () => void
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null)
  const [checkingSession, setCheckingSession] = useState(true)
  const [sessionError, setSessionError] = useState('')
  const mountedRef = useRef(false)
  const sessionRequestRef = useRef<Promise<void> | null>(null)
  const sessionControllerRef = useRef<AbortController | null>(null)

  const checkSession = useCallback(() => {
    if (sessionRequestRef.current) return sessionRequestRef.current

    const controller = new AbortController()
    sessionControllerRef.current = controller
    const request = apiRequest<AuthResponse>('/api/auth/me', { signal: controller.signal })
      .then((response) => {
        if (!mountedRef.current || controller.signal.aborted) return
        setUser(response.user)
        setSessionError('')
      })
      .catch((error: unknown) => {
        if (!mountedRef.current || controller.signal.aborted) return
        if (error instanceof ApiError && error.status === 401) {
          setUser(null)
          setSessionError('')
          return
        }
        setSessionError('로그인 상태를 확인하지 못했습니다. 서버 연결을 확인한 뒤 다시 시도해 주세요.')
      })
      .finally(() => {
        if (sessionRequestRef.current === request) sessionRequestRef.current = null
        if (sessionControllerRef.current === controller) sessionControllerRef.current = null
      })
    sessionRequestRef.current = request
    return request
  }, [])

  useEffect(() => {
    mountedRef.current = true
    setUnauthorizedHandler(checkSession)
    void checkSession()
      .finally(() => {
        if (mountedRef.current) setCheckingSession(false)
      })
    return () => {
      mountedRef.current = false
      setUnauthorizedHandler(null)
      sessionControllerRef.current?.abort()
      sessionControllerRef.current = null
      sessionRequestRef.current = null
    }
  }, [checkSession])

  const login = useCallback(async (loginId: string, password: string) => {
    const response = await apiRequest<AuthResponse>('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ login: loginId, password }),
    })
    setUser(response.user)
    setSessionError('')
  }, [])

  const logout = useCallback(async () => {
    await apiRequest<{ success: boolean }>('/api/auth/logout', { method: 'POST' })
    setUser(null)
  }, [])

  const retrySession = useCallback(() => {
    setCheckingSession(true)
    setSessionError('')
    void checkSession().finally(() => {
      if (mountedRef.current) setCheckingSession(false)
    })
  }, [checkSession])
  const value = useMemo(
    () => ({ user, checkingSession, sessionError, login, logout, retrySession }),
    [user, checkingSession, sessionError, login, logout, retrySession],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

// oxlint-disable-next-line react/only-export-components -- Provider와 전용 훅은 같은 Context를 공유한다.
export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth는 AuthProvider 안에서 사용해야 합니다.')
  return context
}
