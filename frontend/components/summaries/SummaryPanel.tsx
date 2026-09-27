'use client'

import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiFetch } from '@/lib/api'
import { FlagBadge } from '@/components/summaries/FlagBadge'
import type {
  DocumentSummary,
  SummaryAudience,
  SummaryVersion,
} from '@/types/summaries'

const PENDING_POLL_MS = 4000
const DISCLAIMER =
  'Informational only — not a diagnosis. Generated from the confirmed values in this report. ' +
  'Discuss any decision with your doctor.'

function List({ items }: { items?: string[] }) {
  if (!items?.length) return <p className="muted">None noted.</p>
  return (
    <ul className="summary-list">
      {items.map((item, i) => (
        <li key={i}>{item}</li>
      ))}
    </ul>
  )
}

function DoctorContent({ summary }: { summary: DocumentSummary }) {
  const c = summary.content ?? {}
  return (
    <div className="summary-body">
      <section>
        <h3>Chief findings</h3>
        <List items={c.chief_findings} />
      </section>
      <section>
        <h3>Abnormal values</h3>
        {c.abnormal_values?.length ? (
          <div className="review-table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Test</th>
                  <th>Value</th>
                  <th>Reference</th>
                  <th>Flag</th>
                  <th>Previous</th>
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
          <p className="muted">No values outside the reference range.</p>
        )}
      </section>
      <section>
        <h3>Medications</h3>
        <List items={c.medications} />
      </section>
      <section>
        <h3>Items to review</h3>
        <List items={c.items_to_review} />
      </section>
    </div>
  )
}

function PatientContent({ summary }: { summary: DocumentSummary }) {
  const c = summary.content ?? {}
  return (
    <div className="summary-body">
      {c.overview && <p className="summary-overview">{c.overview}</p>}
      <section>
        <h3>Your results, explained</h3>
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
          <p className="muted">No individual results to explain.</p>
        )}
      </section>
      {c.what_this_means && (
        <section>
          <h3>What this means</h3>
          <p>{c.what_this_means}</p>
        </section>
      )}
      <section>
        <h3>Questions you might ask your doctor</h3>
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
  const [version, setVersion] = useState<number | null>(null)

  const versionsQuery = useQuery({
    queryKey: ['summary-versions', documentId],
    queryFn: () => apiFetch<SummaryVersion[]>(`/api/v1/summaries/${documentId}/versions`),
  })
  const summaryQuery = useQuery({
    queryKey: ['summary', documentId, audience, version],
    queryFn: () =>
      apiFetch<DocumentSummary>(
        `/api/v1/summaries/${documentId}?audience=${audience}${version ? `&version=${version}` : ''}`,
      ),
    refetchInterval: (query) =>
      query.state.data?.status === 'pending' ? PENDING_POLL_MS : false,
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
          queryKey: ['summary', documentId, audience, null],
          queryFn: () =>
            apiFetch<DocumentSummary>(`/api/v1/summaries/${documentId}?audience=${audience}`),
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

  return (
    <section className="panel summary-panel">
      <div className="summary-head">
        <p className="summary-disclaimer">{DISCLAIMER}</p>
        <div className="summary-controls">
          {versions.length > 1 && (
            <label className="muted">
              Version{' '}
              <select
                value={version ?? ''}
                onChange={(e) => setVersion(e.target.value ? Number(e.target.value) : null)}
              >
                <option value="">Latest</option>
                {versions.map((v) => (
                  <option key={v.id} value={v.version_no}>
                    v{v.version_no} · {new Date(v.generated_at).toLocaleDateString()}
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
              {busy ? 'Regenerating…' : 'Regenerate'}
            </button>
          )}
        </div>
      </div>

      {summaryQuery.isLoading && <p className="muted">Loading summary…</p>}
      {summaryQuery.isError && (
        <p className="form-error">Could not load this summary. Refresh to try again.</p>
      )}
      {summary?.status === 'pending' && (
        <p className="muted">Generating summary… this usually takes under a minute.</p>
      )}
      {summary?.status === 'failed' && (
        <p className="form-error">
          {summary.error_message || 'The summary could not be generated.'}
          {canRegenerate ? ' Use Regenerate to try again.' : ''}
        </p>
      )}
      {regenerate.isError && (
        <p className="form-error">Could not start regeneration. Try again shortly.</p>
      )}
      {summary?.status === 'ready' &&
        (audience === 'doctor' ? (
          <DoctorContent summary={summary} />
        ) : (
          <PatientContent summary={summary} />
        ))}
      {summary?.status === 'ready' && summary.generated_at && (
        <p className="muted summary-meta">
          Version {summary.version_no} · generated {new Date(summary.generated_at).toLocaleString()}
        </p>
      )}
    </section>
  )
}
