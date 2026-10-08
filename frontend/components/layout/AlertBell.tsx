'use client'

import { useEffect, useRef, useState } from 'react'
import Link from 'next/link'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiFetch } from '@/lib/api'
import { useLocale, useT } from '@/lib/i18n'
import { useAuth } from '@/components/providers/AuthProvider'
import { FlagBadge } from '@/components/summaries/FlagBadge'
import type { Alert } from '@/types/alerts'

const UNREAD_POLL_MS = 60_000
const LIST_STALE_MS = 15_000

function BellIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
      <path
        d="M6 8a6 6 0 0 1 12 0c0 4 1.5 5.5 2 6H4c.5-.5 2-2 2-6Z"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M10 18a2 2 0 0 0 4 0"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

function AlertRow({ alert }: { alert: Alert }) {
  const t = useT()
  const locale = useLocale()
  return (
    <li className={`alert-row${alert.acknowledged_at ? '' : ' unread'}`}>
      <div className="alert-row-head">
        <strong>{alert.field_name}</strong>
        <FlagBadge flag={alert.severity} />
      </div>
      <p className="mono alert-row-value">
        {alert.value} {alert.unit ?? ''}
        {alert.reference_text && (
          <span className="muted"> · {t('alerts.reference')} {alert.reference_text}</span>
        )}
      </p>
      <div className="alert-row-foot">
        <Link href={`/documents/${alert.document_id}`}>
          {alert.document_name ?? t('alerts.viewReport')}
        </Link>
        <span className="muted">
          {new Date(alert.created_at).toLocaleDateString(locale)}
        </span>
      </div>
    </li>
  )
}

export function AlertBell() {
  const { user } = useAuth()
  const t = useT()
  const queryClient = useQueryClient()
  const [open, setOpen] = useState(false)
  const rootRef = useRef<HTMLDivElement | null>(null)
  const enabled = Boolean(user) && user?.role !== 'admin'

  const countQuery = useQuery({
    queryKey: ['alerts-unread-count'],
    queryFn: () => apiFetch<{ count: number }>('/api/v1/alerts/unread-count'),
    enabled,
    refetchInterval: UNREAD_POLL_MS,
  })
  const listQuery = useQuery({
    queryKey: ['alerts'],
    queryFn: () => apiFetch<Alert[]>('/api/v1/alerts'),
    enabled: enabled && open,
    staleTime: LIST_STALE_MS,
  })

  const markAll = useMutation({
    mutationFn: () => apiFetch<{ acknowledged: number }>('/api/v1/alerts/acknowledge-all', { method: 'POST' }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['alerts'] })
      void queryClient.invalidateQueries({ queryKey: ['alerts-unread-count'] })
    },
  })

  useEffect(() => {
    if (!open) return
    function onClick(e: MouseEvent) {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false)
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', onClick)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onClick)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  if (!enabled) return null
  const count = countQuery.data?.count ?? 0
  const alerts = listQuery.data ?? []

  return (
    <div className="alert-bell" ref={rootRef}>
      <button
        type="button"
        className="alert-bell-btn"
        aria-label={count > 0 ? t('alerts.unreadAria', { count }) : t('alerts.title')}
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        <BellIcon />
        {count > 0 && <span className="alert-bell-badge">{count > 9 ? '9+' : count}</span>}
      </button>
      {open && (
        <div className="alert-dropdown" role="dialog" aria-label={t('alerts.title')}>
          <div className="alert-dropdown-head">
            <h3>{t('alerts.title')}</h3>
            {count > 0 && (
              <button
                type="button"
                className="btn btn-ghost"
                disabled={markAll.isPending}
                onClick={() => markAll.mutate()}
              >
                {t('alerts.markAllRead')}
              </button>
            )}
          </div>
          {listQuery.isLoading && <p className="muted">{t('alerts.loading')}</p>}
          {listQuery.isError && <p className="form-error">{t('alerts.failed')}</p>}
          {listQuery.isSuccess && alerts.length === 0 && (
            <p className="muted">{t('alerts.empty')}</p>
          )}
          {alerts.length > 0 && (
            <ul className="alert-list">
              {alerts.map((a) => (
                <AlertRow key={a.id} alert={a} />
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  )
}
