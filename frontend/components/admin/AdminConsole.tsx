'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { apiFetch } from '@/lib/api'
import type { AdminUser, AuditLog, PipelineHealth, UserStatus } from '@/types/auth'

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

function AuditLogViewer() {
  const [logs, setLogs] = useState<AuditLog[]>([])
  const [resource, setResource] = useState('')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const q = resource ? `?resource=${encodeURIComponent(resource)}` : ''
    setLoading(true)
    void apiFetch<AuditLog[]>(`/api/v1/admin/audit-logs${q}`)
      .then(setLogs)
      .finally(() => setLoading(false))
  }, [resource])

  return (
    <div className="panel">
      <div style={{ marginBottom: '1.5rem' }}>
        <div className="eyebrow" style={{ marginBottom: '0.5rem' }}>Compliance</div>
        <h3 style={{ margin: 0 }}>Audit trail</h3>
        <p style={{ color: 'var(--ink-soft)', fontSize: '14px', marginTop: '0.5rem' }}>
          Metadata only — no clinical field values are logged.
        </p>
      </div>

      <label style={{ maxWidth: '300px' }}>
        Filter by resource type
        <input 
          value={resource} 
          onChange={(e) => setResource(e.target.value)} 
          placeholder="user, consent_grant…" 
        />
      </label>

      {loading ? (
        <div className="loading">Loading audit logs…</div>
      ) : (
        <div style={{ overflowX: 'auto' }}>
          <table className="data-table">
            <thead>
              <tr>
                <th>Time</th>
                <th>Actor</th>
                <th>Action</th>
                <th>Resource</th>
              </tr>
            </thead>
            <tbody>
              {logs.length === 0 ? (
                <tr>
                  <td colSpan={4} style={{ textAlign: 'center', color: 'var(--ink-soft)' }}>
                    No audit logs found
                  </td>
                </tr>
              ) : (
                logs.map((l) => (
                  <tr key={l.id}>
                    <td style={{ whiteSpace: 'nowrap' }}>
                      {new Date(l.created_at).toLocaleString()}
                    </td>
                    <td className="mono">{l.actor_id?.slice(0, 8) ?? '—'}</td>
                    <td>
                      <span className="badge badge-normal">{l.action}</span>
                    </td>
                    <td className="mono">
                      {l.resource_type}/{l.resource_id?.slice(0, 8)}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

function PipelineHealthDashboard({ health }: { health: PipelineHealth | null }) {
  if (!health) return null
  
  return (
    <div className="panel">
      <div style={{ marginBottom: '1.5rem' }}>
        <div className="eyebrow" style={{ marginBottom: '0.5rem' }}>System</div>
        <h3 style={{ margin: 0 }}>Pipeline health</h3>
      </div>

      <div className="stat-row">
        <div className="stat-card">
          <div className="value">{health.pending}</div>
          <div className="label">Pending</div>
        </div>
        <div className="stat-card">
          <div className="value" style={{ color: 'var(--teal)' }}>{health.running}</div>
          <div className="label">Running</div>
        </div>
        <div className="stat-card">
          <div className="value" style={{ color: 'var(--coral)' }}>{health.failed}</div>
          <div className="label">Failed</div>
        </div>
        <div className="stat-card">
          <div className="value" style={{ color: 'var(--gold)' }}>{health.retrying}</div>
          <div className="label">Retrying</div>
        </div>
        <div className="stat-card">
          <div className="value" style={{ color: 'var(--teal-deep)' }}>{health.succeeded}</div>
          <div className="label">Succeeded</div>
        </div>
      </div>

      {health.recent_failures.length > 0 && (
        <div style={{ marginTop: '1rem' }}>
          <h4 style={{ fontSize: '14px', marginBottom: '0.75rem' }}>Recent failures</h4>
          <ul className="grant-list">
            {health.recent_failures.map((f) => (
              <li key={f.id} style={{ flexDirection: 'column', alignItems: 'flex-start' }}>
                <span className="badge badge-watch">{f.status}</span>
                <span style={{ fontSize: '13px', marginTop: '0.5rem' }}>
                  {f.error_message ?? 'Unknown error'}
                </span>
                <span style={{ fontSize: '12px', color: 'var(--ink-soft)' }}>
                  Retries: {f.retry_count}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}

function UserManagement() {
  const [users, setUsers] = useState<AdminUser[]>([])
  const [statusFilter, setStatusFilter] = useState<UserStatus | ''>('pending_verification')
  const [loading, setLoading] = useState(true)

  async function loadUsers() {
    setLoading(true)
    const q = statusFilter ? `?status=${statusFilter}` : ''
    try {
      setUsers(await apiFetch<AdminUser[]>(`/api/v1/admin/users${q}`))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void loadUsers()
  }, [statusFilter])

  async function approveDoctor(id: string) {
    await apiFetch(`/api/v1/admin/users/${id}/approve-doctor`, { method: 'POST' })
    await loadUsers()
  }

  return (
    <div className="panel">
      <div style={{ marginBottom: '1.5rem' }}>
        <div className="eyebrow" style={{ marginBottom: '0.5rem' }}>User management</div>
        <h3 style={{ margin: 0 }}>Users</h3>
      </div>

      <label style={{ maxWidth: '250px', marginBottom: '1rem' }}>
        Status filter
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value as UserStatus | '')}
        >
          <option value="">All users</option>
          <option value="pending_verification">Pending verification</option>
          <option value="active">Active</option>
          <option value="suspended">Suspended</option>
        </select>
      </label>

      {loading ? (
        <div className="loading">Loading users…</div>
      ) : (
        <div style={{ overflowX: 'auto' }}>
          <table className="data-table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Email</th>
                <th>Role</th>
                <th>Status</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {users.length === 0 ? (
                <tr>
                  <td colSpan={5} style={{ textAlign: 'center', color: 'var(--ink-soft)' }}>
                    No users found
                  </td>
                </tr>
              ) : (
                users.map((u) => (
                  <tr key={u.id}>
                    <td style={{ fontWeight: 500 }}>{u.full_name}</td>
                    <td style={{ color: 'var(--ink-soft)' }}>{u.email}</td>
                    <td>
                      <span className="badge badge-normal">{u.role}</span>
                    </td>
                    <td>
                      <span className={`badge ${u.status === 'active' ? 'badge-normal' : u.status === 'pending_verification' ? 'badge-pending' : 'badge-watch'}`}>
                        {u.status}
                      </span>
                    </td>
                    <td>
                      {u.role === 'doctor' && u.status === 'pending_verification' && (
                        <button 
                          type="button" 
                          className="btn btn-teal"
                          style={{ fontSize: '12px', padding: '6px 12px' }}
                          onClick={() => void approveDoctor(u.id)}
                        >
                          Approve
                        </button>
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

export function AdminConsole() {
  const [health, setHealth] = useState<PipelineHealth | null>(null)

  useEffect(() => {
    void apiFetch<PipelineHealth>('/api/v1/admin/pipeline-health').then(setHealth)
  }, [])

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
            <Link href="/admin">Admin</Link>
          </div>
          <div className="nav-cta">
            <Link href="/dashboard" className="btn btn-ghost">Back to dashboard</Link>
          </div>
        </div>
      </nav>
      
      <div className="dashboard">
        <header className="dash-header">
          <div>
            <div className="eyebrow">Administration</div>
            <h1>Admin console</h1>
            <p className="muted">Manage users, review audit logs, and monitor system health.</p>
          </div>
        </header>

        <UserManagement />
        <PipelineHealthDashboard health={health} />
        <AuditLogViewer />
      </div>
    </>
  )
}
