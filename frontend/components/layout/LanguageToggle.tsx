'use client'

import { useDocumentLanguage, useLanguageStore, type Language } from '@/lib/language'

const OPTIONS: Array<{ value: Language; label: string; title: string }> = [
  { value: 'en', label: 'EN', title: 'English' },
  { value: 'bn', label: 'বাংলা', title: 'Bangla' },
]

export function LanguageToggle() {
  const language = useLanguageStore((s) => s.language)
  const setLanguage = useLanguageStore((s) => s.setLanguage)
  useDocumentLanguage()

  return (
    <div className="lang-toggle" role="group" aria-label="Language">
      {OPTIONS.map((option) => (
        <button
          key={option.value}
          type="button"
          title={option.title}
          aria-pressed={language === option.value}
          className={language === option.value ? 'active' : ''}
          onClick={() => setLanguage(option.value)}
        >
          {option.label}
        </button>
      ))}
    </div>
  )
}
