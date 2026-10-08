import type { LabFlag } from '@/types/trends'

export interface Alert {
  id: string
  document_id: string
  patient_id: string
  metric_key: string
  field_name: string
  value: string
  unit?: string | null
  reference_text?: string | null
  severity: Extract<LabFlag, 'abnormal' | 'critical'>
  observed_at?: string | null
  created_at: string
  acknowledged_at?: string | null
  document_label?: string | null
  document_name?: string | null
}
