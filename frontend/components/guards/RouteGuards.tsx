'use client'

import { useEffect, type ReactNode } from 'react'
import { useRouter } from 'next/navigation'
import { useAuth } from '@/components/providers/AuthProvider'
import type { UserRole } from '@/types/auth'

export function GuestGuard({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth()
  const router = useRouter()

  useEffect(() => {
    if (!loading && user) router.replace('/dashboard')
  }, [user, loading, router])

  if (loading) return <p className="loading">Loading…</p>
  if (user) return null
  return children
}

export function AuthGuard({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth()
  const router = useRouter()

  useEffect(() => {
    if (!loading && !user) router.replace('/login')
  }, [user, loading, router])

  if (loading) return <p className="loading">Checking session…</p>
  if (!user) return null
  return children
}

export function RoleGuard({
  roles,
  children,
}: {
  roles: UserRole[]
  children: ReactNode
}) {
  const { user, loading } = useAuth()
  const router = useRouter()

  useEffect(() => {
    if (!loading && user && !roles.includes(user.role)) {
      router.replace('/dashboard')
    }
  }, [user, loading, roles, router])

  if (loading) return <p className="loading">Checking session…</p>
  if (!user || !roles.includes(user.role)) return null
  return children
}
