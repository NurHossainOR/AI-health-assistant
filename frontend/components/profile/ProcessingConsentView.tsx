'use client'

import { useState } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { apiFetch } from '@/lib/api'
import { AppNav } from '@/components/layout/AppNav'

export function ProcessingConsentView() {
  const router = useRouter()
  const params = useSearchParams()
  const next = params.get('next') || '/upload'
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function accept() {
    setPending(true)
    setError(null)
    try {
      await apiFetch('/api/v1/consent/processing', { method: 'POST' })
      router.replace(next)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not save consent')
    } finally {
      setPending(false)
    }
  }

  return (
    <>
      <AppNav />
      <div className="dashboard">
        <section className="panel" style={{ maxWidth: '640px' }}>
          <div className="eyebrow">Required before upload</div>
          <h1>Data-processing consent</h1>
          <p className="muted">
            Spondon extracts text and structured values from documents you upload so we can explain
            results and track changes over time. This is separate from sharing records with a doctor.
          </p>
          <ul className="consent-bullets">
            <li>You can export or delete your data at any time from Privacy.</li>
            <li>AI outputs are informational only — not a diagnosis.</li>
            <li>Files are stored encrypted in transit; access is logged.</li>
          </ul>
          {error && <p className="form-error">{error}</p>}
          <button type="button" onClick={() => void accept()} disabled={pending} style={{ maxWidth: '280px' }}>
            {pending ? 'Saving…' : 'I agree — continue to upload'}
          </button>
        </section>
      </div>
    </>
  )
}
