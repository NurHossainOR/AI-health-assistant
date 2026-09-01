export type UserRole = 'patient' | 'doctor' | 'caregiver' | 'admin'

export type UserStatus =
  | 'active'
  | 'pending_verification'
  | 'suspended'
  | 'pending_email'

export type ConsentScope =
  | 'all'
  | 'labs'
  | 'imaging'
  | 'prescriptions'
  | 'discharge'

export interface User {
  id: string
  email: string
  full_name: string
  role: UserRole
  status: UserStatus
  email_verified: boolean
  mfa_enabled: boolean
  created_at: string
}

export interface TokenResponse {
  access_token: string
  token_type: string
  expires_in: number
  mfa_required: boolean
  user: User | null
}

export interface ConsentGrant {
  id: string
  patient_id: string
  grantee_id: string
  scope: ConsentScope
  scope_detail?: Record<string, unknown> | null
  expires_at?: string | null
  granted_at: string
  revoked_at?: string | null
  grantee_name?: string | null
  patient_name?: string | null
  preview?: { label: string; includes: string[] } | null
}

export interface AuditLog {
  id: string
  actor_id: string | null
  action: string
  resource_type: string
  resource_id: string | null
  ip_address: string | null
  metadata: Record<string, unknown> | null
  created_at: string
}

export interface AdminUser extends User {
  bmdc_registration_number?: string | null
  specialty?: string | null
  verified_at?: string | null
}

export interface PipelineHealth {
  total: number
  pending: number
  running: number
  succeeded: number
  failed: number
  retrying: number
  recent_failures: Array<{
    id: string
    document_id: string | null
    status: string
    error_message: string | null
    retry_count: number
    updated_at: string | null
  }>
}
