'use client'

import { type FormEvent, useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { apiFetch } from '@/lib/api'
import type { UserRole } from '@/types/auth'

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

export function SignupForm() {
  const router = useRouter()
  const [fullName, setFullName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [role, setRole] = useState<UserRole>('patient')
  const [npi, setNpi] = useState('')
  const [specialty, setSpecialty] = useState('')
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setMessage(null)
    setPending(true)
    try {
      const res = await apiFetch<{ message: string }>('/api/v1/auth/register', {
        method: 'POST',
        body: JSON.stringify({
          email,
          password,
          full_name: fullName,
          role,
          bmdc_registration_number: role === 'doctor' ? npi || null : null,
          specialty: role === 'doctor' ? specialty || null : null,
        }),
      })
      setMessage(res.message)
      setTimeout(() => router.push('/login'), 2500)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Registration failed')
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
        <div className="eyebrow">Get started</div>
        <h1>Create account</h1>
        <p className="lede">Choose your role. Providers require admin verification.</p>
      </header>

      {error && <p className="form-error">{error}</p>}
      {message && <p className="form-success">{message}</p>}

      <label>
        Full name
        <input 
          value={fullName} 
          onChange={(e) => setFullName(e.target.value)} 
          placeholder="Your full name"
          required 
        />
      </label>

      <label>
        Email
        <input 
          type="email" 
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
          minLength={8}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="Min. 8 characters"
          required
        />
      </label>

      <fieldset className="role-picker">
        <legend>I am a</legend>
        {(['patient', 'doctor', 'caregiver'] as UserRole[]).map((r) => (
          <label key={r} className="role-option">
            <input
              type="radio"
              name="role"
              value={r}
              checked={role === r}
              onChange={() => setRole(r)}
            />
            <span>{r.charAt(0).toUpperCase() + r.slice(1)}</span>
          </label>
        ))}
      </fieldset>

      {role === 'doctor' && (
        <>
          <label>
            NPI number
            <input 
              value={npi} 
              onChange={(e) => setNpi(e.target.value)} 
              placeholder="Optional — helps verify your credentials" 
            />
          </label>
          <label>
            Specialty
            <input
              value={specialty}
              onChange={(e) => setSpecialty(e.target.value)}
              placeholder="e.g. Internal Medicine"
            />
          </label>
        </>
      )}

      <button type="submit" disabled={pending}>
        {pending ? 'Creating account…' : 'Create account'}
      </button>

      <p className="form-footer">
        Already registered? <Link href="/login">Sign in</Link>
      </p>
    </form>
  )
}
