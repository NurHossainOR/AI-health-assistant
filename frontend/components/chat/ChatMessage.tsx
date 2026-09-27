'use client'

import Link from 'next/link'
import type { ChatCitation, ChatMessage as ChatMessageType } from '@/types/chat'

function citationForIndex(index: number, citations: ChatCitation[]) {
  return citations.find((c) => c.source_index === index)
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
                  <Link
                    key={`${part.citation.document_id}-${i}`}
                    href={`/documents/${part.citation.document_id}`}
                    className="cite"
                  >
                    {part.citation.label}
                  </Link>
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
            <Link
              key={`${citation.document_id}-${citation.source_index}`}
              href={`/documents/${citation.document_id}`}
              className="cite"
            >
              {citation.label}
            </Link>
          ))}
        </div>
      )}
    </article>
  )
}
