'use client'

import type { ChatSession } from '@/types/chat'

export function ChatSessionList({
  sessions,
  activeId,
  onSelect,
  onNew,
}: {
  sessions: ChatSession[]
  activeId: string | null
  onSelect: (id: string) => void
  onNew: () => void
}) {
  return (
    <aside className="chat-sidebar">
      <div className="chat-sidebar-head">
        <h2>Chats</h2>
        <button type="button" className="btn btn-teal" onClick={onNew}>
          New chat
        </button>
      </div>
      {sessions.length === 0 ? (
        <p className="muted">No previous questions yet.</p>
      ) : (
        <ul className="chat-session-list">
          {sessions.map((session) => (
            <li key={session.id}>
              <button
                type="button"
                className={session.id === activeId ? 'active' : ''}
                onClick={() => onSelect(session.id)}
              >
                <span>{session.title}</span>
                <small>{new Date(session.updated_at).toLocaleDateString()}</small>
              </button>
            </li>
          ))}
        </ul>
      )}
    </aside>
  )
}
