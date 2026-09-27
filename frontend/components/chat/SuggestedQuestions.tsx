import { SUGGESTED_QUESTIONS } from '@/types/chat'

export function SuggestedQuestions({
  onSelect,
  disabled,
}: {
  onSelect: (question: string) => void
  disabled?: boolean
}) {
  return (
    <div className="chat-suggestions">
      <p className="muted">Try asking</p>
      <div className="chat-suggestion-row">
        {SUGGESTED_QUESTIONS.map((question) => (
          <button
            key={question}
            type="button"
            className="chat-suggestion"
            disabled={disabled}
            onClick={() => onSelect(question)}
          >
            {question}
          </button>
        ))}
      </div>
    </div>
  )
}
