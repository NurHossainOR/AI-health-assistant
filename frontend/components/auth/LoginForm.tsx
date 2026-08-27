'use client'

import { type FormEvent, useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useAuth } from '@/components/providers/AuthProvider'

function SpondonLogo() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none">
      <path
        d="M2 12h5l2-7 4 14 3-10 2 3h4"
        stroke="#0E6F64"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

export function LoginForm() {
  const { login } = useAuth()
  const router = useRouter()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [mfaCode, setMfaCode] = useState('')
  const [mfaRequired, setMfaRequired] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setPending(true)
    try {
      const res = await login(email, password, mfaRequired ? mfaCode : undefined)
      if (res.mfa_required) {
        setMfaRequired(true)
      } else {
        router.push('/dashboard')
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed')
    } finally {
      setPending(false)
    }
  }

  return (
    <form className="auth-form" onSubmit={onSubmit}>
      <header>
        <Link href="/" className="logo" style={{ marginBottom: '1rem', display: 'inline-flex' }}>
          <SpondonLogo />
          Spondon
        </Link>
        <div className="eyebrow">Welcome back</div>
        <h1>Sign in</h1>
        <p className="lede">Secure access to your health records and insights.</p>
      </header>

      {error && <p className="form-error">{error}</p>}

      <label>
        Email
        <input
          type="email"
          autoComplete="username"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="you@example.com"
          required
        />
      </label>

      <label>
        Password
        <input
          type="password"
          autoComplete="current-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="••••••••"
          required
        />
      </label>

      {mfaRequired && (
        <label>
          Authentication code
          <input
            inputMode="numeric"
            autoComplete="one-time-code"
            value={mfaCode}
            onChange={(e) => setMfaCode(e.target.value)}
            placeholder="6-digit code"
            required
          />
        </label>
      )}

      <button type="submit" disabled={pending}>
        {pending ? 'Signing in…' : mfaRequired ? 'Verify & sign in' : 'Sign in'}
      </button>

      <p className="form-footer">
        No account? <Link href="/signup">Create one</Link>
      </p>
    </form>
  )
}
