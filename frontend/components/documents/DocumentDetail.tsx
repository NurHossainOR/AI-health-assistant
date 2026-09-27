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
import { useLocale, useT } from '@/lib/i18n'
import {
  DOC_TYPE_LABELS,
  documentDisplayName,
  type ExtractedField,
  type HealthDocument,
} from '@/types/documents'

type Tab = 'patient' | 'doctor' | 'fields' | 'compare'

const CONFIRMABLE_STATUSES = ['extracted', 'needs_review', 'validating']

function ExtractedDataTable({ documentId }: { documentId: string }) {
  const t = useT()
  const query = useQuery({
    queryKey: ['extracted-fields', documentId],
    queryFn: () => apiFetch<ExtractedField[]>(`/api/v1/documents/${documentId}/extracted-fields`),
  })
  if (query.isLoading) return <p className="muted">{t('fields.loading')}</p>
  if (query.isError) return <p className="form-error">{t('fields.failed')}</p>
  const fields = (query.data ?? []).filter((f) => f.name !== 'Needs manual review')
  if (!fields.length) return <p className="muted">{t('fields.empty')}</p>
  return (
    <div className="review-table-wrap">
      <table className="data-table">
        <thead>
          <tr>
            <th>{t('col.name')}</th>
            <th>{t('col.value')}</th>
            <th>{t('col.reference')}</th>
            <th>{t('col.date')}</th>
            <th>{t('col.flag')}</th>
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
  const t = useT()
  const locale = useLocale()
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
    return <main className="dashboard"><p className="muted">{t('doc.loading')}</p></main>
  }
  if (!doc) {
    return (
      <main className="dashboard">
        <p className="form-error">{t('doc.notFound')}</p>
        <Link href="/dashboard" className="btn btn-ghost">{t('doc.back')}</Link>
      </main>
    )
  }

  const confirmed = doc.status === 'confirmed'
  const tabs: Array<{ key: Tab; label: string }> = [
    { key: 'patient', label: t('tab.patient') },
    { key: 'doctor', label: t('tab.doctor') },
    { key: 'fields', label: t('tab.fields') },
    { key: 'compare', label: t('tab.compare') },
  ]

  return (
    <main className="dashboard">
      <header className="dash-header">
        <div>
          <p className="eyebrow">{DOC_TYPE_LABELS[doc.doc_type]}</p>
          <h1>{documentDisplayName(doc)}</h1>
          <p className="muted">
            {t('doc.uploaded')} {new Date(doc.uploaded_at).toLocaleDateString(locale)}
            {doc.confirmed_at &&
              ` · ${t('doc.confirmed')} ${new Date(doc.confirmed_at).toLocaleDateString(locale)}`}
          </p>
        </div>
        <div className="dash-actions">
          <button
            type="button"
            className="btn btn-ghost"
            onClick={() => {
              setOpenError(null)
              openDocumentFile(doc.id).catch(() => setOpenError(t('doc.openFailed')))
            }}
          >
            {t('doc.openOriginal')}
          </button>
          <Link href={user.role === 'patient' ? '/trends' : `/trends?patient=${doc.patient_id}`} className="btn btn-primary">
            {t('doc.viewTrends')}
          </Link>
        </div>
      </header>
      {openError && <p className="form-error">{openError}</p>}

      {!confirmed && isOwner && CONFIRMABLE_STATUSES.includes(doc.status) ? (
        <>
          <section className="panel">
            <p className="muted">
              {t('doc.confirmPrompt')}
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
              ? t('doc.processing', { status: doc.status.replace('_', ' ') })
              : t('doc.awaitingPatient')}
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
