'use client'

import { useEffect, useState } from 'react'
import { useSearchParams } from 'next/navigation'
import Link from 'next/link'
import { apiFetch } from '@/lib/api'
import { AuthLayout } from '@/components/layout/AuthLayout'

export function VerifyEmailForm() {
  const params = useSearchParams()
  const token = params.get('token') ?? ''
  const [status, setStatus] = useState<'pending' | 'ok' | 'error'>(token ? 'pending' : 'error')
  const [message, setMessage] = useState(token ? 'Verifying your email…' : 'Missing verification token.')

  useEffect(() => {
    if (!token) return
    void (async () => {
      try {
        const res = await apiFetch<{ message: string }>('/api/v1/auth/verify-email', {
          method: 'POST',
          body: JSON.stringify({ token }),
        })
        setStatus('ok')
        setMessage(res.message)
      } catch (e) {
        setStatus('error')
        setMessage(e instanceof Error ? e.message : 'Verification failed')
      }
    })()
  }, [token])

  return (
    <AuthLayout>
      <div className="auth-form">
        <div className="eyebrow">Account</div>
        <h1>Email verification</h1>
        <p className={status === 'error' ? 'form-error' : status === 'ok' ? 'form-success' : 'lede'}>
          {message}
        </p>
        {status === 'ok' && (
          <p className="form-footer">
            <Link href="/login">Continue to sign in</Link>
          </p>
        )}
        {status === 'error' && (
          <p className="form-footer">
            <Link href="/login">Back to sign in</Link>
          </p>
        )}
      </div>
    </AuthLayout>
  )
}
