export type LabFlag = 'normal' | 'borderline' | 'abnormal' | 'critical' | 'unknown'

export interface TrendMetric {
  key: string
  name: string
  unit?: string | null
  point_count: number
  latest_value?: number | null
  latest_flag?: LabFlag | null
  latest_date?: string | null
}

export interface TrendPoint {
  date: string
  value: number
  raw_value: string
  unit?: string | null
  flag: LabFlag
  reference_low?: number | null
  reference_high?: number | null
  document_id: string
  document_name: string
  previous?: number | null
  delta?: number | null
  pct_change?: number | null
  direction?: 'up' | 'down' | 'flat' | null
  zscore?: number | null
  significant_change: boolean
}

export interface TrendSeries {
  key: string
  name: string
  unit?: string | null
  reference_low?: number | null
  reference_high?: number | null
  points: TrendPoint[]
}

export interface TrendsResponse {
  patient_id: string
  series: TrendSeries[]
}

export interface CompareRow {
  metric_key: string
  name: string
  unit?: string | null
  value: number
  raw_value: string
  flag: LabFlag
  reference_low?: number | null
  reference_high?: number | null
  previous_value?: number | null
  previous_flag?: LabFlag | null
  previous_date?: string | null
  delta?: number | null
  pct_change?: number | null
  direction?: 'up' | 'down' | 'flat' | null
}

export interface CompareResponse {
  document_id: string
  against_document_id?: string | null
  rows: CompareRow[]
}

export const FLAG_COLORS: Record<LabFlag, string> = {
  normal: '#0E6F64',
  borderline: '#B9902A',
  abnormal: '#E1583F',
  critical: '#9F1D1D',
  unknown: '#8A8A8A',
}

export function formatReference(low?: number | null, high?: number | null) {
  if (low != null && high != null) return `${low}–${high}`
  if (high != null) return `< ${high}`
  if (low != null) return `> ${low}`
  return '—'
}
