'use client'

import { type FormEvent, useState } from 'react'
import Link from 'next/link'
import { apiFetch } from '@/lib/api'

export function ForgotPasswordForm() {
  const [email, setEmail] = useState('')
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setPending(true)
    setError(null)
    setMessage(null)
    try {
      const res = await apiFetch<{ message: string }>('/api/v1/auth/password-reset', {
        method: 'POST',
        body: JSON.stringify({ email }),
      })
      setMessage(res.message)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Request failed')
    } finally {
      setPending(false)
    }
  }

  return (
    <form className="auth-form" onSubmit={onSubmit}>
      <header>
        <div className="eyebrow">Account recovery</div>
        <h1>Reset password</h1>
        <p className="lede">Enter your email and we&apos;ll send a reset link if an account exists.</p>
      </header>
      {error && <p className="form-error">{error}</p>}
      {message && <p className="form-success">{message}</p>}
      <label>
        Email
        <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
      </label>
      <button type="submit" disabled={pending}>
        {pending ? 'Sending…' : 'Send reset link'}
      </button>
      <p className="form-footer">
        <Link href="/login">Back to sign in</Link>
      </p>
    </form>
  )
}
