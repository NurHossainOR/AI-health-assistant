'use client'

import { useEffect, useMemo, useState } from 'react'
import { apiFetch } from '@/lib/api'
import type { ConsentGrant, VerifiedDoctor } from '@/types/auth'
import type { HealthDocument } from '@/types/documents'
import {
  DOC_TYPE_LABELS,
  SHAREABLE_STATUSES,
  documentDisplayName,
  documentShareLabel,
} from '@/types/documents'

function doctorOptionLabel(d: VerifiedDoctor) {
  return d.bmdc_registration_number
    ? `${d.full_name} (BMDC ${d.bmdc_registration_number})`
    : d.full_name
}

function grantLabel(g: ConsentGrant) {
  return g.preview?.label ?? (g.scope === 'document' ? 'Shared document' : g.scope)
}

export function ConsentManager() {
  const [grants, setGrants] = useState<ConsentGrant[]>([])
  const [doctors, setDoctors] = useState<VerifiedDoctor[]>([])
  const [documents, setDocuments] = useState<HealthDocument[]>([])
  const [granteeId, setGranteeId] = useState('')
  const [documentId, setDocumentId] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)

  const shareable = useMemo(
    () => documents.filter((d) => SHAREABLE_STATUSES.includes(d.status)),
    [documents],
  )

  const selectedDoc = shareable.find((d) => d.id === documentId)

  async function load() {
    const [grantData, doctorData, docData] = await Promise.all([
      apiFetch<ConsentGrant[]>('/api/v1/consent/grants'),
      apiFetch<VerifiedDoctor[]>('/api/v1/consent/doctors'),
      apiFetch<HealthDocument[]>('/api/v1/documents'),
    ])
    setGrants(grantData)
    setDoctors(doctorData)
    setDocuments(docData)
  }

  useEffect(() => {
    void load().catch((e) => setError(e instanceof Error ? e.message : 'Failed to load sharing'))
  }, [])

  async function grantAccess() {
    setError(null)
    setPending(true)
    try {
      await apiFetch('/api/v1/consent/grants', {
        method: 'POST',
        body: JSON.stringify({
          grantee_id: granteeId,
          scope: 'document',
          scope_detail: { document_id: documentId },
        }),
      })
      setDocumentId('')
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
  const canGrant = Boolean(granteeId && documentId) && !pending

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
          Doctor
          <select value={granteeId} onChange={(e) => setGranteeId(e.target.value)} disabled={doctors.length === 0}>
            <option value="">
              {doctors.length === 0 ? 'No verified doctors yet' : 'Select a doctor'}
            </option>
            {doctors.map((d) => (
              <option key={d.id} value={d.id}>
                {doctorOptionLabel(d)}
              </option>
            ))}
          </select>
        </label>
        <label>
          Scope
          <select
            value={documentId}
            onChange={(e) => setDocumentId(e.target.value)}
            disabled={shareable.length === 0}
          >
            <option value="">
              {shareable.length === 0
                ? 'Upload a report first to share it'
                : 'Select a document'}
            </option>
            {shareable.map((d) => (
              <option key={d.id} value={d.id}>
                {documentShareLabel(documentDisplayName(d), d.uploaded_at)}
              </option>
            ))}
          </select>
        </label>

        {selectedDoc && (
          <div className="scope-preview">
            <strong style={{ display: 'block', marginBottom: '0.5rem' }}>
              {documentShareLabel(documentDisplayName(selectedDoc), selectedDoc.uploaded_at)}
            </strong>
            <ul style={{ paddingLeft: '1.25rem', margin: 0, color: 'var(--ink-soft)' }}>
              <li style={{ marginBottom: '0.25rem' }}>
                {DOC_TYPE_LABELS[selectedDoc.doc_type]}
              </li>
            </ul>
          </div>
        )}

        <button
          type="button"
          onClick={() => void grantAccess()}
          disabled={!canGrant}
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
                  <span className="badge badge-normal" style={{ marginLeft: '8px' }}>
                    {grantLabel(g)}
                  </span>
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
