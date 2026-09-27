import { getAccessToken, refreshAccessToken } from '@/lib/api'
import type { ChatCitation } from '@/types/chat'

export type ChatStreamEvent =
  | { event: 'meta'; data: { intent?: string; insufficient_context: boolean; citations: ChatCitation[] } }
  | { event: 'token'; data: { text: string } }
  | {
      event: 'done'
      data: {
        message_id: string
        insufficient_context: boolean
        citations: ChatCitation[]
        cited_document_ids: string[]
      }
    }
  | { event: 'error'; data: { detail: string; code?: string } }

function parseSseBlock(block: string): ChatStreamEvent | null {
  let event = 'message'
  const dataLines: string[] = []
  for (const line of block.split('\n')) {
    if (line.startsWith('event:')) event = line.slice(6).trim()
    else if (line.startsWith('data:')) dataLines.push(line.slice(5).trim())
  }
  if (!dataLines.length) return null
  try {
    const data = JSON.parse(dataLines.join('\n'))
    return { event, data } as ChatStreamEvent
  } catch {
    return null
  }
}

export async function streamChatMessage(
  sessionId: string,
  content: string,
  onEvent: (event: ChatStreamEvent) => void,
  signal?: AbortSignal,
  language: 'en' | 'bn' = 'en',
): Promise<void> {
  const send = async () => {
    const headers = new Headers({ 'Content-Type': 'application/json' })
    const token = getAccessToken()
    if (token) headers.set('Authorization', `Bearer ${token}`)
    return fetch(`/api/v1/chat/sessions/${sessionId}/messages`, {
      method: 'POST',
      headers,
      credentials: 'include',
      body: JSON.stringify({ content, language }),
      signal,
    })
  }

  let res = await send()
  if (res.status === 401) {
    try {
      await refreshAccessToken()
      res = await send()
    } catch {
      throw new Error('Session expired. Please sign in again.')
    }
  }
  if (!res.ok || !res.body) {
    let detail = 'Could not send the message'
    try {
      const payload = await res.json()
      detail = payload?.detail ?? detail
    } catch {
      /* ignore */
    }
    throw new Error(detail)
  }

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  while (true) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const parts = buffer.split('\n\n')
    buffer = parts.pop() ?? ''
    for (const part of parts) {
      const parsed = parseSseBlock(part.trim())
      if (parsed) onEvent(parsed)
    }
  }
  if (buffer.trim()) {
    const parsed = parseSseBlock(buffer.trim())
    if (parsed) onEvent(parsed)
  }
}
