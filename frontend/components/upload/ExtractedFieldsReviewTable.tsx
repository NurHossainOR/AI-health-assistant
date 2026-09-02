'use client'

import { type FormEvent, useEffect, useState } from 'react'
import { apiFetch } from '@/lib/api'
import type { ExtractedField } from '@/types/documents'

export function ExtractedFieldsReviewTable({
  documentId,
  onConfirmed,
}: {
  documentId: string
  onConfirmed: () => void
}) {
  const [fields, setFields] = useState<ExtractedField[]>([])
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)

  useEffect(() => {
    void (async () => {
      try {
        const data = await apiFetch<ExtractedField[]>(
          `/api/v1/documents/${documentId}/extracted-fields`,
        )
        setFields(data)
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Failed to load fields')
      }
    })()
  }, [documentId])

  function update(idx: number, patch: Partial<ExtractedField>) {
    setFields((rows) => rows.map((r, i) => (i === idx ? { ...r, ...patch } : r)))
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setPending(true)
    setError(null)
    try {
      await apiFetch(`/api/v1/documents/${documentId}/extracted-fields`, {
        method: 'PATCH',
        body: JSON.stringify({ fields }),
      })
      await apiFetch(`/api/v1/documents/${documentId}/confirm`, { method: 'POST' })
      onConfirmed()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not confirm')
    } finally {
      setPending(false)
    }
  }

  return (
    <form className="panel" onSubmit={onSubmit}>
      <div className="eyebrow">Human review</div>
      <h3>Confirm extracted fields</h3>
      <p className="muted">Correct anything the pipeline misread before this report is saved.</p>
      {error && <p className="form-error">{error}</p>}
      <div className="review-table-wrap">
        <table className="data-table">
          <thead>
            <tr>
              <th>Name</th>
              <th>Value</th>
              <th>Unit</th>
              <th>Ref low</th>
              <th>Ref high</th>
              <th>Date</th>
              <th>Conf.</th>
            </tr>
          </thead>
          <tbody>
            {fields.map((f, i) => (
              <tr key={f.id ?? i}>
                <td>
                  <input value={f.name} onChange={(e) => update(i, { name: e.target.value })} required />
                </td>
                <td>
                  <input value={f.value ?? ''} onChange={(e) => update(i, { value: e.target.value })} />
                </td>
                <td>
                  <input value={f.unit ?? ''} onChange={(e) => update(i, { unit: e.target.value })} />
                </td>
                <td>
                  <input
                    inputMode="decimal"
                    value={f.reference_low ?? ''}
                    onChange={(e) => update(i, { reference_low: e.target.value })}
                  />
                </td>
                <td>
                  <input
                    inputMode="decimal"
                    value={f.reference_high ?? ''}
                    onChange={(e) => update(i, { reference_high: e.target.value })}
                  />
                </td>
                <td>
                  <input
                    type="date"
                    value={f.observed_at ?? ''}
                    onChange={(e) => update(i, { observed_at: e.target.value })}
                  />
                </td>
                <td className="mono">{Math.round((f.source_confidence ?? 0) * 100)}%</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <button type="submit" disabled={pending} style={{ maxWidth: '220px', marginTop: '1rem' }}>
        {pending ? 'Saving…' : 'Confirm report'}
      </button>
    </form>
  )
}
