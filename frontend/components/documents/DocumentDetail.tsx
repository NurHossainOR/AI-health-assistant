'use client'

import { useState } from 'react'
import Link from 'next/link'
import { useParams } from 'next/navigation'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { apiFetch } from '@/lib/api'
import { openDocumentFile } from '@/lib/openDocument'
import { useAuth } from '@/components/providers/AuthProvider'
import { FlagBadge } from '@/components/summaries/FlagBadge'
import { SummaryPanel } from '@/components/summaries/SummaryPanel'
import { CompareTable } from '@/components/trends/CompareTable'
import { ExtractedFieldsReviewTable } from '@/components/upload/ExtractedFieldsReviewTable'
import {
  DOC_TYPE_LABELS,
  documentDisplayName,
  type ExtractedField,
  type HealthDocument,
} from '@/types/documents'

type Tab = 'patient' | 'doctor' | 'fields' | 'compare'

const CONFIRMABLE_STATUSES = ['extracted', 'needs_review', 'validating']

function ExtractedDataTable({ documentId }: { documentId: string }) {
  const query = useQuery({
    queryKey: ['extracted-fields', documentId],
    queryFn: () => apiFetch<ExtractedField[]>(`/api/v1/documents/${documentId}/extracted-fields`),
  })
  if (query.isLoading) return <p className="muted">Loading extracted values…</p>
  if (query.isError) return <p className="form-error">Could not load extracted values.</p>
  const fields = (query.data ?? []).filter((f) => f.name !== 'Needs manual review')
  if (!fields.length) return <p className="muted">No structured values were extracted.</p>
  return (
    <div className="review-table-wrap">
      <table className="data-table">
        <thead>
          <tr>
            <th>Name</th>
            <th>Value</th>
            <th>Reference</th>
            <th>Date</th>
            <th>Flag</th>
          </tr>
        </thead>
        <tbody>
          {fields.map((f, i) => (
            <tr key={f.id ?? `${f.name}-${i}`}>
              <td>{f.name}</td>
              <td className="mono">
                {f.value ?? '—'} {f.unit ?? ''}
              </td>
              <td className="mono">
                {f.reference_low || f.reference_high
                  ? `${f.reference_low ?? ''}–${f.reference_high ?? ''}`
                  : '—'}
              </td>
              <td className="mono">{f.observed_at ?? '—'}</td>
              <td>{f.field_type === 'lab' ? <FlagBadge flag={f.flag} /> : <span className="muted">{f.field_type}</span>}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function DocumentDetail() {
  const { id } = useParams<{ id: string }>()
  const { user } = useAuth()
  const queryClient = useQueryClient()
  const [tab, setTab] = useState<Tab | null>(null)
  const [openError, setOpenError] = useState<string | null>(null)

  const docsQuery = useQuery({
    queryKey: ['documents'],
    queryFn: () => apiFetch<HealthDocument[]>('/api/v1/documents'),
    enabled: Boolean(user) && user?.role !== 'admin',
  })
  const doc = docsQuery.data?.find((d) => d.id === id)

  if (!user) return null
  const activeTab: Tab = tab ?? (user.role === 'patient' ? 'patient' : 'doctor')
  const isOwner = user.role === 'patient' && doc?.patient_id === user.id

  if (docsQuery.isLoading) {
    return <main className="dashboard"><p className="muted">Loading report…</p></main>
  }
  if (!doc) {
    return (
      <main className="dashboard">
        <p className="form-error">This report was not found or you don&apos;t have access to it.</p>
        <Link href="/dashboard" className="btn btn-ghost">Back to dashboard</Link>
      </main>
    )
  }

  const confirmed = doc.status === 'confirmed'
  const tabs: Array<{ key: Tab; label: string }> = [
    { key: 'patient', label: 'Patient explanation' },
    { key: 'doctor', label: 'Doctor summary' },
    { key: 'fields', label: 'Extracted data' },
    { key: 'compare', label: 'Compare' },
  ]

  return (
    <main className="dashboard">
      <header className="dash-header">
        <div>
          <p className="eyebrow">{DOC_TYPE_LABELS[doc.doc_type]}</p>
          <h1>{documentDisplayName(doc)}</h1>
          <p className="muted">
            Uploaded {new Date(doc.uploaded_at).toLocaleDateString()}
            {doc.confirmed_at && ` · confirmed ${new Date(doc.confirmed_at).toLocaleDateString()}`}
          </p>
        </div>
        <div className="dash-actions">
          <button
            type="button"
            className="btn btn-ghost"
            onClick={() => {
              setOpenError(null)
              openDocumentFile(doc.id).catch(() => setOpenError('Could not open the original file.'))
            }}
          >
            Open original
          </button>
          <Link href={user.role === 'patient' ? '/trends' : `/trends?patient=${doc.patient_id}`} className="btn btn-primary">
            View trends
          </Link>
        </div>
      </header>
      {openError && <p className="form-error">{openError}</p>}

      {!confirmed && isOwner && CONFIRMABLE_STATUSES.includes(doc.status) ? (
        <>
          <section className="panel">
            <p className="muted">
              Check the extracted values below and confirm the report. Summaries, flags and trends
              are generated from confirmed reports only.
            </p>
          </section>
          <ExtractedFieldsReviewTable
            documentId={doc.id}
            onConfirmed={() => {
              void queryClient.invalidateQueries({ queryKey: ['documents'] })
              void queryClient.invalidateQueries({ queryKey: ['trend-metrics'] })
              void queryClient.invalidateQueries({ queryKey: ['trends'] })
            }}
          />
        </>
      ) : !confirmed ? (
        <section className="panel">
          <p className="muted">
            {isOwner
              ? `This report is still being processed (${doc.status.replace('_', ' ')}). Summaries appear once it is confirmed.`
              : 'Summaries and comparisons appear once the patient confirms this report.'}
          </p>
        </section>
      ) : (
        <>
          <div className="tabs" role="tablist">
            {tabs.map((t) => (
              <button
                key={t.key}
                type="button"
                role="tab"
                aria-selected={activeTab === t.key}
                className={`tab-btn${activeTab === t.key ? ' active' : ''}`}
                onClick={() => setTab(t.key)}
              >
                {t.label}
              </button>
            ))}
          </div>
          {(activeTab === 'patient' || activeTab === 'doctor') && (
            <SummaryPanel
              key={activeTab}
              documentId={doc.id}
              audience={activeTab}
              canRegenerate={isOwner}
            />
          )}
          {activeTab === 'fields' && (
            <section className="panel">
              <ExtractedDataTable documentId={doc.id} />
            </section>
          )}
          {activeTab === 'compare' && (
            <section className="panel">
              <CompareTable documentId={doc.id} />
            </section>
          )}
        </>
      )}
    </main>
  )
}
