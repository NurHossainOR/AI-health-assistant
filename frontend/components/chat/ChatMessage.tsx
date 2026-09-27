'use client'

import { apiFetchBlob } from '@/lib/api'
import type { ChatCitation, ChatMessage as ChatMessageType } from '@/types/chat'

function citationForIndex(index: number, citations: ChatCitation[]) {
  return citations.find((c) => c.source_index === index)
}

async function openDocument(documentId: string) {
  try {
    const { blob } = await apiFetchBlob(`/api/v1/documents/${documentId}/file`)
    const url = URL.createObjectURL(blob)
    window.open(url, '_blank', 'noopener,noreferrer')
    window.setTimeout(() => URL.revokeObjectURL(url), 60_000)
  } catch {
    window.alert('Could not open that document.')
  }
}

function renderContent(content: string, citations: ChatCitation[]) {
  const parts: Array<{ type: 'text' | 'cite'; value: string; citation?: ChatCitation }> = []
  const sourceRe = /\[Source\s+(\d+)\]/g
  let last = 0
  let match: RegExpExecArray | null
  while ((match = sourceRe.exec(content))) {
    if (match.index > last) {
      parts.push({ type: 'text', value: content.slice(last, match.index) })
    }
    const index = Number(match[1])
    parts.push({
      type: 'cite',
      value: match[0],
      citation: citationForIndex(index, citations),
    })
    last = match.index + match[0].length
  }
  if (last < content.length) {
    parts.push({ type: 'text', value: content.slice(last) })
  }
  return parts
}

export function ChatMessage({
  message,
  streaming,
}: {
  message: ChatMessageType
  streaming?: boolean
}) {
  const citations = message.citations ?? []
  const parts = message.role === 'assistant' ? renderContent(message.content, citations) : null
  const shownCitations =
    message.role === 'assistant' && !message.insufficient_context ? citations : []

  return (
    <article
      className={[
        'chat-bubble',
        message.role,
        message.insufficient_context ? 'fallback' : '',
        streaming ? 'streaming' : '',
      ]
        .filter(Boolean)
        .join(' ')}
    >
      {message.role === 'user' ? (
        <p className="chat-bubble-text">{message.content}</p>
      ) : (
        <p className="chat-bubble-text">
          {parts?.length
            ? parts.map((part, i) =>
                part.type === 'cite' && part.citation ? (
                  <button
                    key={`${part.citation.document_id}-${i}`}
                    type="button"
                    className="cite"
                    onClick={() => void openDocument(part.citation!.document_id)}
                  >
                    {part.citation.label}
                  </button>
                ) : part.type === 'cite' ? (
                  <span key={i} className="cite">
                    {part.value}
                  </span>
                ) : (
                  <span key={i}>{part.value}</span>
                ),
              )
            : message.content || (streaming ? '…' : '')}
        </p>
      )}
      {shownCitations.length > 0 && (
        <div className="chat-cite-row">
          {shownCitations.map((citation) => (
            <button
              key={`${citation.document_id}-${citation.source_index}`}
              type="button"
              className="cite"
              onClick={() => void openDocument(citation.document_id)}
            >
              {citation.label}
            </button>
          ))}
        </div>
      )}
    </article>
  )
}
