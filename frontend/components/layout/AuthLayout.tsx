'use client'

import { ReactNode } from 'react'

export function AuthLayout({ children }: { children: ReactNode }) {
  return (
    <div className="auth-shell">
      <div className="auth-visual">
        <div className="auth-visual-inner">
          <span>Every result,<br />understood.</span>
        </div>
      </div>
      <div className="auth-panel">{children}</div>
    </div>
  )
}
