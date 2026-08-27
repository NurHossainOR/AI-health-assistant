'use client'

import { type FormEvent, useEffect, useState } from 'react'
import { apiFetch } from '@/lib/api'

export function MfaSetup() {
  const [secret, setSecret] = useState('')
  const [qr, setQr] = useState('')
  const [code, setCode] = useState('')
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)

  useEffect(() => {
    void (async () => {
      try {
        const data = await apiFetch<{
          secret: string
          otpauth_url: string
          qr_svg_data_uri?: string
        }>('/api/v1/auth/mfa/setup', { method: 'POST' })
        setSecret(data.secret)
        setQr(data.qr_svg_data_uri ?? '')
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Setup failed')
      }
    })()
  }, [])

  async function onVerify(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setPending(true)
    try {
      const res = await apiFetch<{ message: string }>('/api/v1/auth/mfa/verify', {
        method: 'POST',
        body: JSON.stringify({ code }),
      })
      setMessage(res.message)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Verification failed')
    } finally {
      setPending(false)
    }
  }

  return (
    <section className="panel" style={{ maxWidth: '480px' }}>
      <div style={{ marginBottom: '1.5rem' }}>
        <div className="eyebrow" style={{ marginBottom: '0.5rem' }}>Security</div>
        <h2 style={{ margin: 0 }}>Multi-factor authentication</h2>
        <p style={{ color: 'var(--ink-soft)', marginTop: '0.5rem' }}>
          Add an extra layer of security to your account using an authenticator app.
        </p>
      </div>

      {error && <p className="form-error">{error}</p>}
      {message && <p className="form-success">{message}</p>}

      {qr && (
        <div style={{ 
          background: '#fff', 
          padding: '1.5rem', 
          borderRadius: '12px', 
          border: '1px solid var(--line)',
          textAlign: 'center',
          marginBottom: '1.5rem'
        }}>
          <p style={{ fontSize: '14px', color: 'var(--ink-soft)', marginBottom: '1rem' }}>
            Scan this QR code with your authenticator app
          </p>
          <img 
            src={qr} 
            alt="MFA QR code" 
            width={180} 
            height={180} 
            style={{ display: 'block', margin: '0 auto' }}
          />
        </div>
      )}

      {secret && (
        <div style={{ 
          background: 'var(--paper-dim)', 
          padding: '1rem', 
          borderRadius: '8px', 
          marginBottom: '1.5rem' 
        }}>
          <p style={{ fontSize: '13px', color: 'var(--ink-soft)', marginBottom: '0.5rem' }}>
            Or enter this key manually:
          </p>
          <code className="mono" style={{ 
            display: 'block', 
            fontSize: '14px', 
            fontWeight: 600,
            wordBreak: 'break-all'
          }}>
            {secret}
          </code>
        </div>
      )}

      <form onSubmit={onVerify}>
        <label>
          Verification code
          <input 
            value={code} 
            onChange={(e) => setCode(e.target.value)} 
            placeholder="Enter 6-digit code"
            inputMode="numeric"
            autoComplete="one-time-code"
            required 
          />
        </label>
        <button type="submit" disabled={pending || !code}>
          {pending ? 'Verifying…' : 'Enable MFA'}
        </button>
      </form>
    </section>
  )
}
