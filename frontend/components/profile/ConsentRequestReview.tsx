'use client'

import { useEffect, useState } from 'react'
import { apiFetch } from '@/lib/api'
import type { ConsentGrant } from '@/types/auth'

export function ConsentRequestReview() {
  const [grants, setGrants] = useState<ConsentGrant[]>([])
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    void (async () => {
      try {
        setGrants(await apiFetch<ConsentGrant[]>('/api/v1/consent/grants'))
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Failed to load grants')
      } finally {
        setLoading(false)
      }
    })()
  }, [])

  const active = grants.filter((g) => !g.revoked_at)

  return (
    <section className="panel">
      <div style={{ marginBottom: '1.5rem' }}>
        <div className="eyebrow" style={{ marginBottom: '0.5rem' }}>Patient access</div>
        <h2 style={{ margin: 0 }}>Patients who shared with you</h2>
        <p style={{ color: 'var(--ink-soft)', marginTop: '0.5rem' }}>
          View records from patients who have granted you access.
        </p>
      </div>

      {error && <p className="form-error">{error}</p>}
      
      {loading ? (
        <div className="loading">Loading patient grants…</div>
      ) : active.length === 0 ? (
        <div style={{ 
          textAlign: 'center', 
          padding: '3rem 2rem', 
          background: 'var(--paper-dim)', 
          borderRadius: '8px',
          border: '1px dashed var(--line)'
        }}>
          <svg width="48" height="48" viewBox="0 0 24 24" fill="none" style={{ margin: '0 auto 1rem', opacity: 0.5 }}>
            <circle cx="12" cy="8" r="3.5" stroke="#0E6F64" strokeWidth="1.8" />
            <path d="M4 20c0-4 3.5-6 8-6s8 2 8 6" stroke="#0E6F64" strokeWidth="1.8" />
          </svg>
          <p style={{ color: 'var(--ink-soft)', margin: 0 }}>
            No patients have shared their records with you yet.
          </p>
        </div>
      ) : (
        <ul className="grant-list">
          {active.map((g) => (
            <li key={g.id}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                <div className="chip-avatar">
                  {(g.patient_name ?? 'P')[0].toUpperCase()}
                </div>
                <div>
                  <strong>{g.patient_name ?? g.patient_id}</strong>
                  <span className="badge badge-normal" style={{ marginLeft: '8px' }}>{g.scope}</span>
                  {g.expires_at && (
                    <span style={{ display: 'block', fontSize: '12px', color: 'var(--ink-soft)', marginTop: '4px' }}>
                      Access until {new Date(g.expires_at).toLocaleDateString()}
                    </span>
                  )}
                </div>
              </div>
              <button 
                type="button" 
                className="btn btn-teal"
                style={{ fontSize: '13px', padding: '8px 16px' }}
              >
                View records
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
