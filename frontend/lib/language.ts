'use client'

import { useEffect } from 'react'
import { create } from 'zustand'
import { createJSONStorage, persist } from 'zustand/middleware'

export type Language = 'en' | 'bn'

interface LanguageState {
  language: Language
  setLanguage: (language: Language) => void
}

export const useLanguageStore = create<LanguageState>()(
  persist(
    (set) => ({
      language: 'en',
      setLanguage: (language) => set({ language }),
    }),
    { name: 'spondon-language', storage: createJSONStorage(() => localStorage) },
  ),
)

export function useLanguage(): Language {
  return useLanguageStore((s) => s.language)
}

/** Keep <html lang> in sync so screen readers switch pronunciation. */
export function useDocumentLanguage() {
  const language = useLanguage()
  useEffect(() => {
    document.documentElement.lang = language
  }, [language])
}
