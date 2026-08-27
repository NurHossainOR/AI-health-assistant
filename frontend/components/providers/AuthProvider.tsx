'use client'

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
import { apiFetch, setAccessToken } from '@/lib/api'
import type { TokenResponse, User } from '@/types/auth'

const INACTIVITY_MS = 15 * 60 * 1000

interface AuthContextValue {
  user: User | null
  loading: boolean
  login: (email: string, password: string, mfaCode?: string) => Promise<TokenResponse>
  logout: () => Promise<void>
  refreshSession: () => Promise<void>
  setUser: (user: User | null) => void
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)
  const timerRef = useRef<number | null>(null)

  const logout = useCallback(async () => {
    try {
      await apiFetch('/api/v1/auth/logout', { method: 'POST' })
    } catch {
      /* ignore */
    }
    setAccessToken(null)
    setUser(null)
  }, [])

  const refreshSession = useCallback(async () => {
    const data = await apiFetch<TokenResponse>('/api/v1/auth/refresh', {
      method: 'POST',
      body: JSON.stringify({}),
    })
    setAccessToken(data.access_token)
    if (data.user) setUser(data.user)
    else {
      const me = await apiFetch<User>('/api/v1/auth/me')
      setUser(me)
    }
  }, [])

  const resetInactivityTimer = useCallback(() => {
    if (timerRef.current) window.clearTimeout(timerRef.current)
    timerRef.current = window.setTimeout(() => {
      void logout()
    }, INACTIVITY_MS)
  }, [logout])

  useEffect(() => {
    void (async () => {
      try {
        await refreshSession()
      } catch {
        setAccessToken(null)
        setUser(null)
      } finally {
        setLoading(false)
      }
    })()
  }, [refreshSession])

  useEffect(() => {
    if (!user) return
    const events = ['mousemove', 'keydown', 'click', 'scroll', 'touchstart'] as const
    const handler = () => resetInactivityTimer()
    events.forEach((e) => window.addEventListener(e, handler))
    resetInactivityTimer()
    return () => {
      events.forEach((e) => window.removeEventListener(e, handler))
      if (timerRef.current) window.clearTimeout(timerRef.current)
    }
  }, [user, resetInactivityTimer])

  const login = useCallback(
    async (email: string, password: string, mfaCode?: string) => {
      const data = await apiFetch<TokenResponse>('/api/v1/auth/login', {
        method: 'POST',
        body: JSON.stringify({ email, password, mfa_code: mfaCode ?? null }),
      })
      if (!data.mfa_required) {
        setAccessToken(data.access_token)
        setUser(data.user)
        resetInactivityTimer()
      }
      return data
    },
    [resetInactivityTimer],
  )

  const value = useMemo(
    () => ({ user, loading, login, logout, refreshSession, setUser }),
    [user, loading, login, logout, refreshSession],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
