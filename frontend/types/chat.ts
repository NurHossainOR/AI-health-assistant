export interface ChatCitation {
  source_index: number
  document_id: string
  doc_type: string
  label: string
  source_date?: string | null
}

export interface ChatSession {
  id: string
  patient_id: string
  title: string
  created_at: string
  updated_at: string
}

export interface ChatMessage {
  id: string
  session_id: string
  role: 'user' | 'assistant'
  content: string
  cited_document_ids: string[]
  citations?: ChatCitation[] | null
  insufficient_context: boolean
  created_at: string
}

export const SUGGESTED_QUESTIONS = [
  'What were my last three cholesterol readings?',
  'Am I due for a follow-up on my MRI finding?',
  'What medications appear in my records?',
  'What did my most recent blood test show?',
]
