import type { LabFlag } from '@/types/trends'

export type SummaryAudience = 'doctor' | 'patient'
export type SummaryStatus = 'ready' | 'failed' | 'pending'

export interface DoctorSummaryContent {
  chief_findings?: string[]
  abnormal_values?: Array<{
    name: string
    value: string
    unit?: string | null
    reference?: string | null
    flag: LabFlag
    previous?: string | null
    delta?: string | null
  }>
  medications?: string[]
  items_to_review?: string[]
}

export interface PatientSummaryContent {
  overview?: string
  findings?: Array<{
    name: string
    value: string
    unit?: string | null
    flag: LabFlag
    plain_explanation?: string
  }>
  what_this_means?: string
  questions_for_doctor?: string[]
}

export interface DocumentSummary {
  status: SummaryStatus
  document_id: string
  audience: SummaryAudience
  id?: string | null
  version_no?: number | null
  content?: (DoctorSummaryContent & PatientSummaryContent) | null
  model_version?: string | null
  error_message?: string | null
  generated_at?: string | null
  language: 'en' | 'bn'
  translation_pending?: boolean
  translation_failed?: boolean
}

export interface SummaryVersion {
  id: string
  audience: SummaryAudience
  version_no: number
  status: string
  model_version?: string | null
  generated_at: string
}
