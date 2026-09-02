'use client'

import { useState } from 'react'
import { apiFetch } from '@/lib/api'
import { useAuth } from '@/components/providers/AuthProvider'
import { AppNav } from '@/components/layout/AppNav'

export function PrivacyCenter() {
  const { user, logout } = useAuth()
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [confirm, setConfirm] = useState('')
  const [pending, setPending] = useState(false)

  async function exportData() {
    setError(null)
    try {
      const data = await apiFetch<Record<string, unknown>>('/api/v1/users/me/export')
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = 'spondon-export.json'
      a.click()
      URL.revokeObjectURL(url)
      setMessage('Export downloaded.')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Export failed')
    }
  }

  async function deleteAccount() {
    if (!user || confirm !== user.email) {
      setError('Type your email to confirm deletion.')
      return
    }
    setPending(true)
    setError(null)
    try {
      await apiFetch('/api/v1/users/me', { method: 'DELETE' })
      await logout()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Deletion failed')
    } finally {
      setPending(false)
    }
  }

  return (
    <>
      <AppNav />
      <div className="dashboard">
        <header className="dash-header">
          <div>
            <div className="eyebrow">GDPR</div>
            <h1>Privacy & data</h1>
            <p className="muted">Download a copy of your data, or permanently delete your account.</p>
          </div>
        </header>
        {error && <p className="form-error">{error}</p>}
        {message && <p className="form-success">{message}</p>}
        <section className="panel">
          <h2>Export my data</h2>
          <p className="muted">JSON archive of your profile, consent grants, and document extractions.</p>
          <button type="button" onClick={() => void exportData()} style={{ maxWidth: '220px' }}>
            Download export
          </button>
        </section>
        <section className="panel">
          <h2>Delete my account</h2>
          <p className="muted">
            This removes your profile, documents, and consent grants. Type <strong>{user?.email}</strong> to
            confirm.
          </p>
          <label>
            Confirm email
            <input value={confirm} onChange={(e) => setConfirm(e.target.value)} />
          </label>
          <button
            type="button"
            className="btn btn-danger"
            disabled={pending}
            onClick={() => void deleteAccount()}
            style={{ maxWidth: '240px' }}
          >
            {pending ? 'Deleting…' : 'Delete account'}
          </button>
        </section>
      </div>
    </>
  )
}
