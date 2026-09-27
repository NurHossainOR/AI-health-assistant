'use client'

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useMemo, useRef, useState } from 'react'
import { apiFetch } from '@/lib/api'
import { streamChatMessage } from '@/lib/chatStream'
import { useLanguage } from '@/lib/language'
import type { ChatCitation, ChatMessage as ChatMessageType, ChatSession } from '@/types/chat'
import { ChatDisclaimerBanner } from '@/components/chat/ChatDisclaimerBanner'
import { ChatMessage } from '@/components/chat/ChatMessage'
import { ChatSessionList } from '@/components/chat/ChatSessionList'
import { SuggestedQuestions } from '@/components/chat/SuggestedQuestions'

function localId() {
  return `local-${crypto.randomUUID()}`
}

export function ChatWindow() {
  const queryClient = useQueryClient()
  const language = useLanguage()
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [draft, setDraft] = useState('')
  const [liveMessages, setLiveMessages] = useState<ChatMessageType[]>([])
  const [streaming, setStreaming] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const bottomRef = useRef<HTMLDivElement>(null)
  const abortRef = useRef<AbortController | null>(null)

  const sessionsQuery = useQuery({
    queryKey: ['chat-sessions'],
    queryFn: () => apiFetch<ChatSession[]>('/api/v1/chat/sessions?limit=50'),
  })

  const historyQuery = useQuery({
    queryKey: ['chat-messages', sessionId],
    queryFn: () => apiFetch<ChatMessageType[]>(`/api/v1/chat/sessions/${sessionId}/messages?limit=200`),
    enabled: Boolean(sessionId),
  })

  const createSession = useMutation({
    mutationFn: () => apiFetch<ChatSession>('/api/v1/chat/sessions', { method: 'POST', body: JSON.stringify({}) }),
    onSuccess: (session) => {
      setSessionId(session.id)
      setLiveMessages([])
      void queryClient.invalidateQueries({ queryKey: ['chat-sessions'] })
    },
  })

  useEffect(() => {
    if (!sessionId && sessionsQuery.data && sessionsQuery.data.length > 0) {
      setSessionId(sessionsQuery.data[0].id)
    }
  }, [sessionId, sessionsQuery.data])

  const history = historyQuery.data ?? []
  const messages = useMemo(() => {
    if (liveMessages.length === 0) return history
    const liveIds = new Set(liveMessages.map((m) => m.id))
    return [...history.filter((m) => !liveIds.has(m.id)), ...liveMessages]
  }, [history, liveMessages])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'auto' })
  }, [messages.length, sessionId])

  async function ensureSession() {
    if (sessionId) return sessionId
    const session = await createSession.mutateAsync()
    return session.id
  }

  function stopGenerating() {
    abortRef.current?.abort()
  }

  async function send(text: string) {
    const content = text.trim()
    if (!content || streaming) return
    setError(null)
    setDraft('')
    const activeId = await ensureSession()
    const userMessage: ChatMessageType = {
      id: localId(),
      session_id: activeId,
      role: 'user',
      content,
      cited_document_ids: [],
      citations: [],
      insufficient_context: false,
      created_at: new Date().toISOString(),
    }
    const assistantMessage: ChatMessageType = {
      id: localId(),
      session_id: activeId,
      role: 'assistant',
      content: '',
      cited_document_ids: [],
      citations: [],
      insufficient_context: false,
      created_at: new Date().toISOString(),
    }
    setLiveMessages((current) => [...current, userMessage, assistantMessage])
    setStreaming(true)
    const controller = new AbortController()
    abortRef.current = controller
    try {
      await streamChatMessage(
        activeId,
        content,
        (event) => {
          if (event.event === 'meta') {
            setLiveMessages((current) =>
              current.map((m) =>
                m.id === assistantMessage.id
                  ? {
                      ...m,
                      insufficient_context: event.data.insufficient_context,
                      citations: event.data.citations,
                    }
                  : m,
              ),
            )
          } else if (event.event === 'token') {
            setLiveMessages((current) =>
              current.map((m) =>
                m.id === assistantMessage.id ? { ...m, content: m.content + event.data.text } : m,
              ),
            )
          } else if (event.event === 'done') {
            setLiveMessages((current) =>
              current.map((m) =>
                m.id === assistantMessage.id
                  ? {
                      ...m,
                      id: event.data.message_id,
                      insufficient_context: event.data.insufficient_context,
                      citations: event.data.citations as ChatCitation[],
                      cited_document_ids: event.data.cited_document_ids,
                    }
                  : m,
              ),
            )
          } else if (event.event === 'error') {
            setError(event.data.detail)
          }
        },
        controller.signal,
        language,
      )
      await queryClient.invalidateQueries({ queryKey: ['chat-sessions'] })
      await queryClient.invalidateQueries({ queryKey: ['chat-messages', activeId] })
      setLiveMessages([])
    } catch (err) {
      if (controller.signal.aborted) {
        setError('Generation stopped.')
      } else {
        setError(err instanceof Error ? err.message : 'Could not send the message')
      }
      await queryClient.invalidateQueries({ queryKey: ['chat-messages', activeId] })
      setLiveMessages([])
    } finally {
      abortRef.current = null
      setStreaming(false)
    }
  }

  function startNewChat() {
    abortRef.current?.abort()
    setLiveMessages([])
    setError(null)
    void createSession.mutateAsync()
  }

  const empty = messages.length === 0 && !historyQuery.isLoading
  const queryError =
    (sessionsQuery.error instanceof Error && sessionsQuery.error.message) ||
    (historyQuery.error instanceof Error && historyQuery.error.message) ||
    null

  return (
    <div className="chat-page">
      <ChatSessionList
        sessions={sessionsQuery.data ?? []}
        activeId={sessionId}
        onSelect={(id) => {
          abortRef.current?.abort()
          setSessionId(id)
          setLiveMessages([])
          setError(null)
        }}
        onNew={startNewChat}
      />
      <section className="chat-main">
        <ChatDisclaimerBanner />
        <div className="chat-thread" aria-live="polite">
          {empty ? (
            <>
              <div className="chat-empty">
                <h1>Ask about your records</h1>
                <p className="muted">
                  I can look up values and findings from documents you have already confirmed.
                  I cannot diagnose or recommend treatment.
                </p>
              </div>
              <SuggestedQuestions disabled={streaming} onSelect={(q) => void send(q)} />
            </>
          ) : historyQuery.isLoading && liveMessages.length === 0 ? (
            <p className="muted">Loading this conversation…</p>
          ) : (
            messages.map((message, index) => (
              <ChatMessage
                key={message.id}
                message={message}
                streaming={streaming && index === messages.length - 1 && message.role === 'assistant'}
              />
            ))
          )}
          {(error || queryError) && <p className="chat-error">{error || queryError}</p>}
          <div ref={bottomRef} />
        </div>
        <form
          className="chat-composer"
          onSubmit={(e) => {
            e.preventDefault()
            void send(draft)
          }}
        >
          <label className="sr-only" htmlFor="chat-input">
            Ask a question about your records
          </label>
          <textarea
            id="chat-input"
            rows={2}
            value={draft}
            disabled={streaming}
            placeholder="Ask a question about your uploaded records…"
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                void send(draft)
              }
            }}
          />
          {streaming ? (
            <button type="button" className="btn btn-ghost" onClick={stopGenerating}>
              Stop
            </button>
          ) : (
            <button type="submit" className="btn btn-primary" disabled={!draft.trim()}>
              Send
            </button>
          )}
        </form>
      </section>
    </div>
  )
}
