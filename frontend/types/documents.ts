export type DocType =
  | 'blood_test'
  | 'prescription'
  | 'mri'
  | 'ct'
  | 'discharge'
  | 'other'

export type DocumentStatus =
  | 'awaiting_upload'
  | 'uploaded'
  | 'pending'
  | 'scanning'
  | 'extracting'
  | 'validating'
  | 'needs_review'
  | 'extracted'
  | 'confirmed'
  | 'failed'
  | 'retrying'

export interface HealthDocument {
  id: string
  patient_id: string
  uploaded_by: string
  doc_type: DocType
  original_filename: string
  display_name?: string | null
  mime_type: string
  file_size: number
  status: DocumentStatus
  error_message?: string | null
  uploaded_at: string
  confirmed_at?: string | null
  needs_review: boolean
  retry_count: number
  stage?: string
}

export interface ExtractedField {
  id?: string
  field_type: string
  name: string
  value?: string | null
  unit?: string | null
  reference_low?: string | null
  reference_high?: string | null
  observed_at?: string | null
  source_confidence: number
  canonical_code?: string | null
}

export interface ProcessingConsent {
  granted: boolean
  granted_at: string | null
}

export const DOC_TYPE_LABELS: Record<DocType | 'auto', string> = {
  auto: 'Auto-detect',
  blood_test: 'Blood test',
  prescription: 'Prescription',
  mri: 'MRI',
  ct: 'CT',
  discharge: 'Discharge summary',
  other: 'Other',
}

export const SHAREABLE_STATUSES: DocumentStatus[] = ['extracted', 'confirmed', 'needs_review']

export function stemFileName(fileName: string) {
  const i = fileName.lastIndexOf('.')
  if (i <= 0) return fileName
  return fileName.slice(0, i)
}

export function documentShareLabel(name: string, uploadedAt?: string | null) {
  const trimmed = name.trim()
  const date = uploadedAt ? new Date(uploadedAt) : new Date()
  if (!trimmed || Number.isNaN(date.getTime())) return trimmed
  return `${trimmed} · ${date.toLocaleDateString()}`
}

export function documentDisplayName(doc: Pick<HealthDocument, 'display_name' | 'original_filename'>) {
  return (doc.display_name || '').trim() || doc.original_filename
}
