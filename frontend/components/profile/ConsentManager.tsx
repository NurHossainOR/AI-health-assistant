'use client'

import { useEffect, useState } from 'react'
import { apiFetch } from '@/lib/api'
import type { ConsentGrant, ConsentScope } from '@/types/auth'

const SCOPES: ConsentScope[] = ['all', 'labs', 'imaging', 'prescriptions', 'discharge']

const SCOPE_LABELS: Record<ConsentScope, { label: string; includes: string[] }> = {
  all: {
    label: 'All health records',
    includes: ['Labs', 'Imaging', 'Prescriptions', 'Discharge summaries', 'Alerts'],
  },
  labs: { label: 'Lab results only', includes: ['Lab results and trends'] },
  imaging: { label: 'Imaging only', includes: ['MRI/CT studies and findings'] },
  prescriptions: {
    label: 'Prescriptions only',
    includes: ['Medication names, dosages, frequency'],
  },
  discharge: {
    label: 'Discharge summaries only',
    includes: ['Diagnoses, procedures, follow-up instructions'],
  },
}

export function ConsentManager() {
  const [grants, setGrants] = useState<ConsentGrant[]>([])
  const [granteeId, setGranteeId] = useState('')
  const [scope, setScope] = useState<ConsentScope>('all')
  const [preview, setPreview] = useState(SCOPE_LABELS.all)
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)

  async function load() {
    const data = await apiFetch<ConsentGrant[]>('/api/v1/consent/grants')
    setGrants(data)
  }

  useEffect(() => {
    void load().catch((e) => setError(e.message))
  }, [])

  useEffect(() => {
    const match = grants.find((g) => g.scope === scope && g.preview)
    if (match?.preview) setPreview(match.preview)
    else setPreview(SCOPE_LABELS[scope])
  }, [scope, grants])

  async function grantAccess() {
    setError(null)
    setPending(true)
    try {
      await apiFetch('/api/v1/consent/grants', {
        method: 'POST',
        body: JSON.stringify({ grantee_id: granteeId, scope }),
      })
      setGranteeId('')
      await load()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to grant access')
    } finally {
      setPending(false)
    }
  }

  async function revoke(id: string) {
    await apiFetch(`/api/v1/consent/grants/${id}`, { method: 'DELETE' })
    await load()
  }

  const activeGrants = grants.filter((g) => !g.revoked_at)

  return (
    <section className="panel">
      <div style={{ marginBottom: '1.5rem' }}>
        <div className="eyebrow" style={{ marginBottom: '0.5rem' }}>Data sharing</div>
        <h2 style={{ margin: 0 }}>Sharing & consent</h2>
        <p style={{ color: 'var(--ink-soft)', marginTop: '0.5rem' }}>
          Grant a verified doctor access. Review exactly what they can see before confirming.
        </p>
      </div>

      {error && <p className="form-error">{error}</p>}

      <div style={{ display: 'grid', gap: '1rem', marginBottom: '2rem' }}>
        <label>
          Doctor user ID
          <input 
            value={granteeId} 
            onChange={(e) => setGranteeId(e.target.value)} 
            placeholder="Enter the doctor's user ID"
          />
        </label>
        <label>
          Scope
          <select value={scope} onChange={(e) => setScope(e.target.value as ConsentScope)}>
            {SCOPES.map((s) => (
              <option key={s} value={s}>
                {SCOPE_LABELS[s].label}
              </option>
            ))}
          </select>
        </label>
        
        <div className="scope-preview">
          <strong style={{ display: 'block', marginBottom: '0.5rem' }}>{preview.label}</strong>
          <ul style={{ paddingLeft: '1.25rem', margin: 0, color: 'var(--ink-soft)' }}>
            {preview.includes.map((item) => (
              <li key={item} style={{ marginBottom: '0.25rem' }}>{item}</li>
            ))}
          </ul>
        </div>
        
        <button 
          type="button" 
          onClick={() => void grantAccess()}
          disabled={!granteeId || pending}
          style={{ maxWidth: '200px' }}
        >
          {pending ? 'Granting…' : 'Grant access'}
        </button>
      </div>

      <div>
        <h3 style={{ fontSize: '1rem', marginBottom: '1rem' }}>Active grants</h3>
        {activeGrants.length === 0 ? (
          <p style={{ color: 'var(--ink-soft)' }}>No active grants yet.</p>
        ) : (
          <ul className="grant-list">
            {activeGrants.map((g) => (
              <li key={g.id}>
                <div>
                  <strong>{g.grantee_name ?? g.grantee_id}</strong>
                  <span className="badge badge-normal" style={{ marginLeft: '8px' }}>{g.scope}</span>
                  <span style={{ display: 'block', fontSize: '13px', color: 'var(--ink-soft)', marginTop: '4px' }}>
                    Since {new Date(g.granted_at).toLocaleDateString()}
                  </span>
                </div>
                <button 
                  type="button" 
                  className="btn btn-ghost" 
                  onClick={() => void revoke(g.id)}
                  style={{ fontSize: '13px', padding: '6px 12px' }}
                >
                  Revoke
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  )
}
