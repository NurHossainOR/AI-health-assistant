'use client'

import { useState } from 'react'
import { apiFetch } from '@/lib/api'
import { useAuth } from '@/components/providers/AuthProvider'

export function VerifyEmailBanner() {
  const { user } = useAuth()
  const [pending, setPending] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  if (!user || user.email_verified) return null

  async function resend() {
    setPending(true)
    setError(null)
    setMessage(null)
    try {
      const res = await apiFetch<{ message: string }>('/api/v1/auth/resend-verification', {
        method: 'POST',
      })
      setMessage(res.message)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not send verification email')
    } finally {
      setPending(false)
    }
  }

  return (
    <div className="form-error" style={{ display: 'grid', gap: '0.75rem' }}>
      <p style={{ margin: 0 }}>
        Verify your email to unlock uploads. We sent a link to {user.email}. Check spam if you
        don&apos;t see it.
      </p>
      <button
        type="button"
        className="btn btn-ghost"
        style={{ width: 'fit-content' }}
        disabled={pending}
        onClick={() => void resend()}
      >
        {pending ? 'Sending…' : 'Resend verification email'}
      </button>
      {message && <p className="form-success" style={{ margin: 0 }}>{message}</p>}
      {error && <p style={{ margin: 0 }}>{error}</p>}
    </div>
  )
}
