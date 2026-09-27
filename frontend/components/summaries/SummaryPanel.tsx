'use client'

import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiFetch } from '@/lib/api'
import { FlagBadge } from '@/components/summaries/FlagBadge'
import { useLocale, useT } from '@/lib/i18n'
import { useLanguage } from '@/lib/language'
import type {
  DocumentSummary,
  SummaryAudience,
  SummaryVersion,
} from '@/types/summaries'

const PENDING_POLL_MS = 4000
const TRANSLATION_POLL_MS = 5000

function List({ items }: { items?: string[] }) {
  const t = useT()
  if (!items?.length) return <p className="muted">{t('summary.noneNoted')}</p>
  return (
    <ul className="summary-list">
      {items.map((item, i) => (
        <li key={i}>{item}</li>
      ))}
    </ul>
  )
}

function DoctorContent({ summary }: { summary: DocumentSummary }) {
  const t = useT()
  const c = summary.content ?? {}
  return (
    <div className="summary-body">
      <section>
        <h3>{t('summary.chiefFindings')}</h3>
        <List items={c.chief_findings} />
      </section>
      <section>
        <h3>{t('summary.abnormalValues')}</h3>
        {c.abnormal_values?.length ? (
          <div className="review-table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>{t('col.test')}</th>
                  <th>{t('col.value')}</th>
                  <th>{t('col.reference')}</th>
                  <th>{t('col.flag')}</th>
                  <th>{t('col.previous')}</th>
                  <th>Δ</th>
                </tr>
              </thead>
              <tbody>
                {c.abnormal_values.map((row, i) => (
                  <tr key={`${row.name}-${i}`}>
                    <td>{row.name}</td>
                    <td className="mono">
                      {row.value} {row.unit ?? ''}
                    </td>
                    <td className="mono">{row.reference ?? '—'}</td>
                    <td>
                      <FlagBadge flag={row.flag} />
                    </td>
                    <td className="mono">{row.previous ?? '—'}</td>
                    <td className="mono">{row.delta ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="muted">{t('summary.noAbnormal')}</p>
        )}
      </section>
      <section>
        <h3>{t('summary.medications')}</h3>
        <List items={c.medications} />
      </section>
      <section>
        <h3>{t('summary.itemsToReview')}</h3>
        <List items={c.items_to_review} />
      </section>
    </div>
  )
}

function PatientContent({ summary }: { summary: DocumentSummary }) {
  const t = useT()
  const c = summary.content ?? {}
  return (
    <div className="summary-body">
      {c.overview && <p className="summary-overview">{c.overview}</p>}
      <section>
        <h3>{t('summary.resultsExplained')}</h3>
        {c.findings?.length ? (
          <ul className="finding-cards">
            {c.findings.map((f, i) => (
              <li key={`${f.name}-${i}`} className={`finding-card flag-edge-${f.flag ?? 'unknown'}`}>
                <div className="finding-card-head">
                  <strong>{f.name}</strong>
                  <span className="mono">
                    {f.value} {f.unit ?? ''}
                  </span>
                  <FlagBadge flag={f.flag} />
                </div>
                {f.plain_explanation && <p>{f.plain_explanation}</p>}
              </li>
            ))}
          </ul>
        ) : (
          <p className="muted">{t('summary.noFindings')}</p>
        )}
      </section>
      {c.what_this_means && (
        <section>
          <h3>{t('summary.whatThisMeans')}</h3>
          <p>{c.what_this_means}</p>
        </section>
      )}
      <section>
        <h3>{t('summary.questions')}</h3>
        <List items={c.questions_for_doctor} />
      </section>
    </div>
  )
}

export function SummaryPanel({
  documentId,
  audience,
  canRegenerate,
}: {
  documentId: string
  audience: SummaryAudience
  canRegenerate: boolean
}) {
  const queryClient = useQueryClient()
  const t = useT()
  const locale = useLocale()
  const language = useLanguage()
  const [version, setVersion] = useState<number | null>(null)

  const versionsQuery = useQuery({
    queryKey: ['summary-versions', documentId],
    queryFn: () => apiFetch<SummaryVersion[]>(`/api/v1/summaries/${documentId}/versions`),
  })
  const summaryQuery = useQuery({
    queryKey: ['summary', documentId, audience, version, language],
    queryFn: () =>
      apiFetch<DocumentSummary>(
        `/api/v1/summaries/${documentId}?audience=${audience}&lang=${language}${version ? `&version=${version}` : ''}`,
      ),
    placeholderData: (previous) => previous,
    refetchInterval: (query) =>
      query.state.data?.status === 'pending'
        ? PENDING_POLL_MS
        : query.state.data?.translation_pending
          ? TRANSLATION_POLL_MS
          : false,
  })

  const regenerate = useMutation({
    mutationFn: () =>
      apiFetch<{ status: string }>(`/api/v1/summaries/${documentId}/regenerate`, {
        method: 'POST',
      }),
    onSuccess: async () => {
      setVersion(null)
      const before = summaryQuery.data?.version_no ?? 0
      // Poll until a newer version lands, then refresh the version list.
      const poll = async (attempt: number) => {
        const next = await queryClient.fetchQuery({
          queryKey: ['summary', documentId, audience, null, 'en'],
          queryFn: () =>
            apiFetch<DocumentSummary>(`/api/v1/summaries/${documentId}?audience=${audience}&lang=en`),
          staleTime: 0,
        })
        if ((next.version_no ?? 0) > before || attempt >= 20) {
          await queryClient.invalidateQueries({ queryKey: ['summary', documentId] })
          await queryClient.invalidateQueries({ queryKey: ['summary-versions', documentId] })
          return
        }
        window.setTimeout(() => void poll(attempt + 1), PENDING_POLL_MS)
      }
      window.setTimeout(() => void poll(0), PENDING_POLL_MS)
    },
  })

  const versions = (versionsQuery.data ?? []).filter((v) => v.audience === audience)
  const summary = summaryQuery.data
  const busy = regenerate.isPending || (regenerate.isSuccess && summaryQuery.isFetching)
  // Bangla is being translated in the background; the English version is shown meanwhile.
  const translating = language !== 'en' && Boolean(summary?.translation_pending)

  return (
    <section className="panel summary-panel">
      <div className="summary-head">
        <p className="summary-disclaimer">{t('summary.disclaimer')}</p>
        <div className="summary-controls">
          {versions.length > 1 && (
            <label className="muted">
              {t('summary.version')}{' '}
              <select
                value={version ?? ''}
                onChange={(e) => setVersion(e.target.value ? Number(e.target.value) : null)}
              >
                <option value="">{t('summary.latest')}</option>
                {versions.map((v) => (
                  <option key={v.id} value={v.version_no}>
                    v{v.version_no} · {new Date(v.generated_at).toLocaleDateString(locale)}
                  </option>
                ))}
              </select>
            </label>
          )}
          {canRegenerate && summary?.status !== 'pending' && (
            <button
              type="button"
              className="btn btn-ghost"
              disabled={busy}
              onClick={() => regenerate.mutate()}
            >
              {busy ? t('summary.regenerating') : t('summary.regenerate')}
            </button>
          )}
        </div>
      </div>

      {translating && <p className="muted">{t('summary.translating')}</p>}
      {summaryQuery.isLoading && <p className="muted">{t('summary.loading')}</p>}
      {summaryQuery.isError && <p className="form-error">{t('summary.loadFailed')}</p>}
      {summary?.translation_failed && (
        <p className="form-error">{t('summary.translationFailed')}</p>
      )}
      {summary?.status === 'pending' && <p className="muted">{t('summary.pending')}</p>}
      {summary?.status === 'failed' && (
        <p className="form-error">
          {language === 'en' && summary.error_message ? summary.error_message : t('summary.failed')}
          {canRegenerate ? t('summary.retryHint') : ''}
        </p>
      )}
      {regenerate.isError && <p className="form-error">{t('summary.regenerateFailed')}</p>}
      {summary?.status === 'ready' &&
        (audience === 'doctor' ? (
          <DoctorContent summary={summary} />
        ) : (
          <PatientContent summary={summary} />
        ))}
      {summary?.status === 'ready' && summary.generated_at && (
        <p className="muted summary-meta">
          {t('summary.meta', {
            version: summary.version_no ?? '',
            date: new Date(summary.generated_at).toLocaleString(locale),
          })}
        </p>
      )}
    </section>
  )
}
