'use client'

import Link from 'next/link'
import type { ReactNode } from 'react'
import { useAuth } from '@/components/providers/AuthProvider'

function SpondonLogo() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none">
      <path
        d="M2 12h5l2-7 4 14 3-10 2 3h4"
        stroke="#0E6F64"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

export function AppNav({ extra }: { extra?: ReactNode }) {
  const { user, logout } = useAuth()

  return (
    <nav>
      <div className="nav-inner">
        <Link href="/" className="logo">
          <SpondonLogo />
          Spondon
        </Link>
        <div className="nav-links">
          <Link href="/dashboard">Dashboard</Link>
          {user?.role === 'patient' && <Link href="/upload">Upload</Link>}
          {user?.role === 'patient' && <Link href="/chat">Ask records</Link>}
          {user && <Link href="/privacy">Privacy</Link>}
          <Link href="/mfa">MFA settings</Link>
          {user?.role === 'admin' && <Link href="/admin">Admin console</Link>}
        </div>
        <div className="nav-cta">
          {extra}
          {user && (
            <span style={{ fontSize: '14px', color: 'var(--ink-soft)' }}>{user.full_name}</span>
          )}
          {user && (
            <button type="button" className="btn btn-ghost" onClick={() => void logout()}>
              Sign out
            </button>
          )}
        </div>
      </div>
    </nav>
  )
}
