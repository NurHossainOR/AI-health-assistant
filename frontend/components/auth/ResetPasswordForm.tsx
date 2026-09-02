'use client'

import { type FormEvent, useState } from 'react'
import Link from 'next/link'
import { useSearchParams, useRouter } from 'next/navigation'
import { apiFetch } from '@/lib/api'

export function ResetPasswordForm() {
  const params = useSearchParams()
  const router = useRouter()
  const token = params.get('token') ?? ''
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [pending, setPending] = useState(false)

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setPending(true)
    setError(null)
    try {
      const res = await apiFetch<{ message: string }>('/api/v1/auth/password-reset/confirm', {
        method: 'POST',
        body: JSON.stringify({ token, new_password: password }),
      })
      setMessage(res.message)
      setTimeout(() => router.push('/login'), 1500)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Reset failed')
    } finally {
      setPending(false)
    }
  }

  if (!token) {
    return (
      <div className="auth-form">
        <h1>Reset password</h1>
        <p className="form-error">This reset link is missing a token.</p>
        <p className="form-footer">
          <Link href="/forgot-password">Request a new link</Link>
        </p>
      </div>
    )
  }

  return (
    <form className="auth-form" onSubmit={onSubmit}>
      <header>
        <div className="eyebrow">Account recovery</div>
        <h1>Choose a new password</h1>
      </header>
      {error && <p className="form-error">{error}</p>}
      {message && <p className="form-success">{message}</p>}
      <label>
        New password
        <input
          type="password"
          minLength={8}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
        />
      </label>
      <button type="submit" disabled={pending}>
        {pending ? 'Updating…' : 'Update password'}
      </button>
    </form>
  )
}
