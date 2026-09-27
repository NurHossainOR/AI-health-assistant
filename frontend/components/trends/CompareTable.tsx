'use client'

import { useQuery } from '@tanstack/react-query'
import { apiFetch } from '@/lib/api'
import { FlagBadge } from '@/components/summaries/FlagBadge'
import { useLocale, useT } from '@/lib/i18n'
import { formatReference, type CompareResponse } from '@/types/trends'

const ARROWS = { up: '↑', down: '↓', flat: '→' } as const

export function CompareTable({ documentId }: { documentId: string }) {
  const t = useT()
  const locale = useLocale()
  const query = useQuery({
    queryKey: ['trend-compare', documentId],
    queryFn: () =>
      apiFetch<CompareResponse>(`/api/v1/trends/compare?document_id=${documentId}`),
  })

  if (query.isLoading) return <p className="muted">{t('compare.loading')}</p>
  if (query.isError) return <p className="form-error">{t('compare.failed')}</p>
  const rows = query.data?.rows ?? []
  if (!rows.length) return <p className="muted">{t('compare.empty')}</p>
  const hasPrevious = rows.some((r) => r.previous_value != null)

  return (
    <div className="review-table-wrap">
      {!hasPrevious && (
        <p className="muted" style={{ marginBottom: '0.75rem' }}>
          {t('compare.noPrevious')}
        </p>
      )}
      <table className="data-table">
        <thead>
          <tr>
            <th>{t('col.test')}</th>
            <th>{t('col.thisReport')}</th>
            <th>{t('col.previous')}</th>
            <th>{t('col.change')}</th>
            <th>{t('col.reference')}</th>
            <th>{t('col.flag')}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.metric_key}>
              <td>{row.name}</td>
              <td className="mono">
                {row.raw_value} {row.unit ?? ''}
              </td>
              <td className="mono">
                {row.previous_value != null ? (
                  <>
                    {row.previous_value}
                    {row.previous_date && (
                      <span className="muted"> · {new Date(row.previous_date).toLocaleDateString(locale)}</span>
                    )}
                  </>
                ) : (
                  '—'
                )}
              </td>
              <td className="mono">
                {row.direction ? (
                  <span className={`delta ${row.flag === 'normal' ? 'ok' : 'up'}`}>
                    {ARROWS[row.direction]} {row.delta != null && row.delta > 0 ? '+' : ''}
                    {row.delta}
                    {row.pct_change != null && ` (${row.pct_change > 0 ? '+' : ''}${row.pct_change}%)`}
                  </span>
                ) : (
                  '—'
                )}
              </td>
              <td className="mono">{formatReference(row.reference_low, row.reference_high)}</td>
              <td>
                <FlagBadge flag={row.flag} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
