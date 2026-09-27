'use client'

import { useMemo, useState } from 'react'
import Link from 'next/link'
import { useSearchParams } from 'next/navigation'
import { useQuery } from '@tanstack/react-query'
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceArea,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { apiFetch } from '@/lib/api'
import { useAuth } from '@/components/providers/AuthProvider'
import { FlagBadge } from '@/components/summaries/FlagBadge'
import type { ConsentGrant } from '@/types/auth'
import {
  FLAG_COLORS,
  formatReference,
  type TrendMetric,
  type TrendPoint,
  type TrendSeries,
  type TrendsResponse,
} from '@/types/trends'

const RANGES = [
  { key: '3m', label: '3 months' },
  { key: '6m', label: '6 months' },
  { key: '1y', label: '1 year' },
  { key: '2y', label: '2 years' },
  { key: 'all', label: 'All time' },
] as const
const MAX_DEFAULT_METRICS = 3

function formatDate(iso: string) {
  return new Date(`${iso}T00:00:00`).toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
    year: '2-digit',
  })
}

const compactNumber = new Intl.NumberFormat(undefined, {
  notation: 'compact',
  maximumFractionDigits: 1,
})

function formatTick(value: number) {
  return Math.abs(value) >= 10_000 ? compactNumber.format(value) : String(value)
}

function FlagDot(props: { cx?: number; cy?: number; payload?: TrendPoint }) {
  const { cx, cy, payload } = props
  if (cx == null || cy == null || !payload) return null
  const color = FLAG_COLORS[payload.flag] ?? FLAG_COLORS.unknown
  return (
    <circle
      cx={cx}
      cy={cy}
      r={payload.significant_change ? 6 : 4.5}
      fill={color}
      stroke="#fff"
      strokeWidth={1.5}
    />
  )
}

function PointTooltip({ active, payload }: { active?: boolean; payload?: Array<{ payload: TrendPoint }> }) {
  const point = active ? payload?.[0]?.payload : undefined
  if (!point) return null
  return (
    <div className="trend-tooltip">
      <strong>
        {point.raw_value} {point.unit ?? ''}
      </strong>
      <span>{formatDate(point.date)}</span>
      <FlagBadge flag={point.flag} />
      {point.delta != null && (
        <span className="mono">
          Δ {point.delta > 0 ? '+' : ''}
          {point.delta}
          {point.pct_change != null && ` (${point.pct_change > 0 ? '+' : ''}${point.pct_change}%)`}
        </span>
      )}
      {point.significant_change && <span className="mono">Unusual vs your baseline</span>}
      <span className="muted">{point.document_name}</span>
    </div>
  )
}

function SeriesChart({ series }: { series: TrendSeries }) {
  const values = series.points.map((p) => p.value)
  const bounds = [...values, series.reference_low, series.reference_high].filter(
    (v): v is number => v != null,
  )
  const min = Math.min(...bounds)
  const max = Math.max(...bounds)
  const pad = (max - min || Math.abs(max) || 1) * 0.15
  const domain: [number, number] = [Math.max(0, min - pad), max + pad]
  const refLow = series.reference_low ?? domain[0]
  const refHigh = series.reference_high ?? domain[1]
  const hasBand = series.reference_low != null || series.reference_high != null

  return (
    <section className="panel trend-card">
      <div className="trend-card-head">
        <div>
          <h3>{series.name}</h3>
          <p className="muted">
            Reference {formatReference(series.reference_low, series.reference_high)}{' '}
            {series.unit ?? ''}
          </p>
        </div>
        <FlagBadge flag={series.points[series.points.length - 1]?.flag} />
      </div>
      <div className="trend-chart" aria-hidden="true">
        <ResponsiveContainer width="100%" height={220}>
          <LineChart data={series.points} margin={{ top: 10, right: 16, bottom: 0, left: -8 }}>
            <CartesianGrid stroke="#EDE7DC" vertical={false} />
            {hasBand && (
              <ReferenceArea
                y1={refLow}
                y2={refHigh}
                fill="#0E6F64"
                fillOpacity={0.08}
                stroke="none"
                ifOverflow="extendDomain"
              />
            )}
            <XAxis dataKey="date" tickFormatter={formatDate} tick={{ fontSize: 11 }} />
            <YAxis domain={domain} tick={{ fontSize: 11 }} tickFormatter={formatTick} width={48} />
            <Tooltip content={<PointTooltip />} />
            <Line
              type="monotone"
              dataKey="value"
              stroke="#1E2A2A"
              strokeWidth={2}
              dot={<FlagDot />}
              activeDot={{ r: 7 }}
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <details className="trend-table-toggle">
        <summary>Show data table</summary>
        <table className="data-table">
          <caption className="sr-only">{series.name} readings</caption>
          <thead>
            <tr>
              <th>Date</th>
              <th>Value</th>
              <th>Change</th>
              <th>Flag</th>
              <th>Report</th>
            </tr>
          </thead>
          <tbody>
            {[...series.points].reverse().map((p) => (
              <tr key={`${p.document_id}-${p.date}`}>
                <td className="mono">{formatDate(p.date)}</td>
                <td className="mono">
                  {p.raw_value} {p.unit ?? ''}
                </td>
                <td className="mono">
                  {p.delta != null ? `${p.delta > 0 ? '+' : ''}${p.delta}` : '—'}
                </td>
                <td>
                  <FlagBadge flag={p.flag} />
                </td>
                <td>
                  <Link href={`/documents/${p.document_id}`}>{p.document_name}</Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </section>
  )
}

export function TrendsView() {
  const { user } = useAuth()
  const searchParams = useSearchParams()
  const isClinician = user?.role === 'doctor' || user?.role === 'caregiver'
  const [patientId, setPatientId] = useState<string | null>(searchParams.get('patient'))
  const [selected, setSelected] = useState<string[] | null>(null)
  const [range, setRange] = useState<string>('all')

  const grantsQuery = useQuery({
    queryKey: ['consent-grants'],
    queryFn: () => apiFetch<ConsentGrant[]>('/api/v1/consent/grants'),
    enabled: isClinician,
  })
  const patients = useMemo(() => {
    const byId = new Map<string, string>()
    for (const g of grantsQuery.data ?? []) {
      if (!g.revoked_at) byId.set(g.patient_id, g.patient_name || 'Patient')
    }
    return [...byId.entries()].map(([id, name]) => ({ id, name }))
  }, [grantsQuery.data])
  const activePatient = isClinician ? patientId ?? patients[0]?.id ?? null : null
  const patientParam = activePatient ? `patient_id=${activePatient}` : ''
  const ready = Boolean(user) && (!isClinician || Boolean(activePatient))

  const metricsQuery = useQuery({
    queryKey: ['trend-metrics', activePatient],
    queryFn: () => apiFetch<TrendMetric[]>(`/api/v1/trends/metrics?${patientParam}`),
    enabled: ready,
  })
  const metrics = metricsQuery.data ?? []
  const chosen =
    selected ??
    metrics
      .filter((m) => m.point_count > 1)
      .concat(metrics.filter((m) => m.point_count <= 1))
      .slice(0, MAX_DEFAULT_METRICS)
      .map((m) => m.key)

  const trendsQuery = useQuery({
    queryKey: ['trends', activePatient, chosen.join(','), range],
    queryFn: () =>
      apiFetch<TrendsResponse>(
        `/api/v1/trends?metrics=${encodeURIComponent(chosen.join(','))}&range=${range}${patientParam ? `&${patientParam}` : ''}`,
      ),
    enabled: ready && chosen.length > 0,
  })

  function toggle(key: string) {
    const current = new Set(chosen)
    if (current.has(key)) current.delete(key)
    else current.add(key)
    setSelected([...current])
  }

  if (!user) return null

  return (
    <main className="dashboard">
      <header className="dash-header">
        <div>
          <p className="eyebrow">Trends &amp; comparisons</p>
          <h1>How your results change over time</h1>
          <p className="muted">
            Shaded bands show the reference range. Dots are colored by flag; larger dots mark
            readings that are unusual compared with earlier results.
          </p>
        </div>
      </header>

      {isClinician && (
        <section className="panel trend-filters">
          {grantsQuery.isLoading ? (
            <p className="muted">Loading patients…</p>
          ) : patients.length === 0 ? (
            <p className="muted">No patients have shared records with you yet.</p>
          ) : (
            <label>
              Patient{' '}
              <select
                value={activePatient ?? ''}
                onChange={(e) => {
                  setPatientId(e.target.value)
                  setSelected(null)
                }}
              >
                {patients.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
            </label>
          )}
        </section>
      )}

      {ready && (
        <section className="panel trend-filters">
          <div className="trend-range" role="group" aria-label="Date range">
            {RANGES.map((r) => (
              <button
                key={r.key}
                type="button"
                className={`tab-btn${range === r.key ? ' active' : ''}`}
                onClick={() => setRange(r.key)}
              >
                {r.label}
              </button>
            ))}
          </div>
          {metricsQuery.isLoading ? (
            <p className="muted">Loading tests…</p>
          ) : metricsQuery.isError ? (
            <p className="form-error">Could not load tests for this patient.</p>
          ) : metrics.length === 0 ? (
            <p className="muted">
              No confirmed lab values yet.{' '}
              {user.role === 'patient' && <Link href="/upload">Upload a blood test</Link>}
            </p>
          ) : (
            <div className="metric-chips">
              {metrics.map((m) => (
                <label key={m.key} className={`metric-chip${chosen.includes(m.key) ? ' on' : ''}`}>
                  <input
                    type="checkbox"
                    checked={chosen.includes(m.key)}
                    onChange={() => toggle(m.key)}
                  />
                  {m.name}
                  <span className="mono">{m.point_count}</span>
                </label>
              ))}
            </div>
          )}
        </section>
      )}

      {trendsQuery.isError && <p className="form-error">Could not load trends.</p>}
      {trendsQuery.isLoading && chosen.length > 0 && <p className="muted">Loading charts…</p>}
      {trendsQuery.data && trendsQuery.data.series.length === 0 && (
        <p className="muted">No readings in this date range.</p>
      )}
      <div className="trend-grid">
        {trendsQuery.data?.series.map((s) => <SeriesChart key={s.key} series={s} />)}
      </div>
    </main>
  )
}
