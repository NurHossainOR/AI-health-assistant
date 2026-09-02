'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { useAuth } from '@/components/providers/AuthProvider'
import { MfaSetup } from '@/components/auth/MfaSetup'
import { ConsentManager } from '@/components/profile/ConsentManager'
import { ConsentRequestReview } from '@/components/profile/ConsentRequestReview'
import { AppNav } from '@/components/layout/AppNav'
import { apiFetch } from '@/lib/api'
import type { HealthDocument } from '@/types/documents'
import { documentDisplayName, documentShareLabel } from '@/types/documents'

export function DashboardView() {
  const { user } = useAuth()
  const [docs, setDocs] = useState<HealthDocument[]>([])

  useEffect(() => {
    if (!user || user.role === 'admin') return
    void apiFetch<HealthDocument[]>('/api/v1/documents')
      .then(setDocs)
      .catch(() => setDocs([]))
  }, [user])

  if (!user) return null

  const last = docs[0]?.uploaded_at
    ? new Date(docs[0].uploaded_at).toLocaleDateString()
    : '—'

  return (
    <>
      <AppNav />
      <div className="dashboard">
        <header className="dash-header">
          <div>
            <div className="eyebrow">Your health hub</div>
            <h1>Welcome, {user.full_name}</h1>
            <p className="muted">
              <span className="badge badge-normal" style={{ marginRight: '8px' }}>
                {user.role}
              </span>
              <span className={`badge ${user.status === 'active' ? 'badge-normal' : 'badge-pending'}`}>
                {user.status}
              </span>
            </p>
          </div>
          {user.role === 'patient' && (
            <Link href="/upload" className="btn btn-primary">
              Upload a report
            </Link>
          )}
        </header>

        {user.role === 'patient' && <ConsentManager />}
        {(user.role === 'doctor' || user.role === 'caregiver') && <ConsentRequestReview />}

        {user.role === 'patient' && (
          <section className="panel">
            <h2>Your health timeline</h2>
            <p style={{ marginBottom: '1rem' }} className="muted">
              {docs.length === 0
                ? 'Upload your first report to get started. We\'ll track it over time and explain what changed.'
                : `${docs.length} document${docs.length === 1 ? '' : 's'} in your record.`}
            </p>
            <div style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap' }}>
              <div className="stat-card">
                <div className="value">{docs.length}</div>
                <div className="label">Reports uploaded</div>
              </div>
              <div className="stat-card">
                <div className="value">{last}</div>
                <div className="label">Last upload</div>
              </div>
              <div className="stat-card">
                <div className="value">{docs.filter((d) => d.status === 'needs_review').length}</div>
                <div className="label">Need review</div>
              </div>
            </div>
          </section>
        )}

        {(user.role === 'doctor' || user.role === 'caregiver') && (
          <section className="panel">
            <h2>Patient records</h2>
            {docs.length === 0 ? (
              <p className="muted">
                Patients who grant you access will appear here. You&apos;ll see their reports in both
                clinical and patient-friendly formats.
              </p>
            ) : (
              <ul className="grant-list">
                {docs.map((d) => (
                  <li key={d.id}>
                    <div>
                      <strong>{documentShareLabel(documentDisplayName(d), d.uploaded_at)}</strong>
                      <span className="badge badge-normal" style={{ marginLeft: '8px' }}>
                        {d.doc_type}
                      </span>
                      <span className="muted" style={{ display: 'block' }}>
                        {d.status} · {new Date(d.uploaded_at).toLocaleDateString()}
                      </span>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </section>
        )}
      </div>
    </>
  )
}

export function MfaView() {
  return (
    <>
      <AppNav extra={<Link href="/dashboard" className="btn btn-ghost">Back to dashboard</Link>} />
      <div className="dashboard">
        <MfaSetup />
      </div>
    </>
  )
}
