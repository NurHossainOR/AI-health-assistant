'use client'

import Link from 'next/link'
import { useAuth } from '@/components/providers/AuthProvider'
import { MfaSetup } from '@/components/auth/MfaSetup'
import { ConsentManager } from '@/components/profile/ConsentManager'
import { ConsentRequestReview } from '@/components/profile/ConsentRequestReview'

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

function DashboardNav() {
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
          <Link href="/mfa">MFA settings</Link>
          {user?.role === 'admin' && <Link href="/admin">Admin console</Link>}
        </div>
        <div className="nav-cta">
          <span style={{ fontSize: '14px', color: 'var(--ink-soft)' }}>
            {user?.full_name}
          </span>
          <button type="button" className="btn btn-ghost" onClick={() => void logout()}>
            Sign out
          </button>
        </div>
      </div>
    </nav>
  )
}

export function DashboardView() {
  const { user } = useAuth()
  if (!user) return null

  return (
    <>
      <DashboardNav />
      <div className="dashboard">
        <header className="dash-header">
          <div>
            <div className="eyebrow">Your health hub</div>
            <h1>Welcome, {user.full_name}</h1>
            <p className="muted">
              <span className="badge badge-normal" style={{ marginRight: '8px' }}>
                {user.role}
              </span>
              <span className={`badge ${user.status === 'active' ? 'badge-normal' : 'badge-pending'}`}>
                {user.status}
              </span>
              {!user.email_verified && (
                <span style={{ marginLeft: '12px', color: 'var(--coral)' }}>
                  Verify your email to unlock uploads
                </span>
              )}
            </p>
          </div>
        </header>

        {user.role === 'patient' && <ConsentManager />}
        {(user.role === 'doctor' || user.role === 'caregiver') && <ConsentRequestReview />}
        
        {user.role === 'patient' && (
          <section className="panel placeholder">
            <h2>Your health timeline</h2>
            <p style={{ marginBottom: '1rem' }}>
              Upload your first report to get started. We&apos;ll track it over time and explain what changed.
            </p>
            <div style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap' }}>
              <div className="stat-card">
                <div className="value">0</div>
                <div className="label">Reports uploaded</div>
              </div>
              <div className="stat-card">
                <div className="value">—</div>
                <div className="label">Last upload</div>
              </div>
              <div className="stat-card">
                <div className="value">0</div>
                <div className="label">Shared with doctors</div>
              </div>
            </div>
          </section>
        )}

        {(user.role === 'doctor' || user.role === 'caregiver') && (
          <section className="panel placeholder">
            <h2>Patient records</h2>
            <p>
              Patients who grant you access will appear here. You&apos;ll see their reports in both clinical 
              and patient-friendly formats.
            </p>
          </section>
        )}
      </div>
    </>
  )
}

export function MfaView() {
  return (
    <>
      <nav>
        <div className="nav-inner">
          <Link href="/" className="logo">
            <SpondonLogo />
            Spondon
          </Link>
          <div className="nav-links">
            <Link href="/dashboard">Dashboard</Link>
          </div>
          <div className="nav-cta">
            <Link href="/dashboard" className="btn btn-ghost">Back to dashboard</Link>
          </div>
        </div>
      </nav>
      <div className="dashboard">
        <MfaSetup />
      </div>
    </>
  )
}
