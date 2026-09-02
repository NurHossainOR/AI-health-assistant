'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { useRouter } from 'next/navigation'
import { apiFetch, getAccessToken } from '@/lib/api'
import { fileStore, useUploadQueueStore, type QueueItem } from '@/lib/uploadQueue'
import { useAuth } from '@/components/providers/AuthProvider'
import type { DocType, HealthDocument, ProcessingConsent } from '@/types/documents'
import { stemFileName } from '@/types/documents'
import { UploadDropzone, asDocTypeHint } from '@/components/upload/UploadDropzone'
import { UploadQueueItem } from '@/components/upload/UploadQueueItem'
import { ExtractedFieldsReviewTable } from '@/components/upload/ExtractedFieldsReviewTable'

async function sha256Hex(file: File) {
  const buf = await file.arrayBuffer()
  const hash = await crypto.subtle.digest('SHA-256', buf)
  return Array.from(new Uint8Array(hash))
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('')
}

function putWithProgress(
  url: string,
  file: File,
  headers: Record<string, string>,
  onProgress: (pct: number) => void,
) {
  return new Promise<void>((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open('PUT', url)
    Object.entries(headers).forEach(([k, v]) => xhr.setRequestHeader(k, v))
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) onProgress(Math.round((e.loaded / e.total) * 90))
    }
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) resolve()
      else reject(new Error(`Upload failed (${xhr.status})`))
    }
    xhr.onerror = () => reject(new Error('Network error during upload'))
    xhr.send(file)
  })
}

function wsUrl(documentId: string, token: string) {
  const explicit = process.env.NEXT_PUBLIC_WS_URL
  if (explicit) return `${explicit}/ws/documents/${documentId}/status?token=${token}`
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${proto}//${window.location.hostname}:8000/ws/documents/${documentId}/status?token=${encodeURIComponent(token)}`
}

export function UploadCenter() {
  const { user } = useAuth()
  const router = useRouter()
  const items = useUploadQueueStore((s) => s.items)
  const patch = useUploadQueueStore((s) => s.patch)
  const applyStatus = useUploadQueueStore((s) => s.applyStatus)
  const [reviewId, setReviewId] = useState<string | null>(null)
  const [gateError, setGateError] = useState<string | null>(null)
  const watchers = useRef<Map<string, () => void>>(new Map())

  useEffect(() => {
    if (!user) return
    void (async () => {
      try {
        const consent = await apiFetch<ProcessingConsent>('/api/v1/consent/processing')
        if (!consent.granted) router.replace('/consent/processing?next=/upload')
      } catch (e) {
        setGateError(e instanceof Error ? e.message : 'Could not check consent')
      }
    })()
  }, [user, router])

  const startWatching = useCallback(
    (documentId: string) => {
      const token = getAccessToken()
      let socket: WebSocket | null = null
      if (token) {
        try {
          socket = new WebSocket(wsUrl(documentId, token))
          socket.onmessage = (ev) => {
            try {
              const data = JSON.parse(ev.data) as HealthDocument
              applyStatus(documentId, data)
              if (data.needs_review || data.status === 'needs_review') setReviewId(documentId)
            } catch {
              /* ignore */
            }
          }
        } catch {
          socket = null
        }
      }
      const poll = window.setInterval(() => {
        void apiFetch<HealthDocument>(`/api/v1/documents/${documentId}/status`)
          .then((data) => {
            applyStatus(documentId, data)
            if (data.needs_review || data.status === 'needs_review') setReviewId(documentId)
            if (['confirmed', 'failed', 'extracted'].includes(data.status)) {
              socket?.close()
              window.clearInterval(poll)
            }
          })
          .catch(() => undefined)
      }, 3000)
      const stop = () => {
        socket?.close()
        window.clearInterval(poll)
      }
      watchers.current.get(documentId)?.()
      watchers.current.set(documentId, stop)
      return stop
    },
    [applyStatus],
  )

  const uploadOne = useCallback(
    async (item: QueueItem) => {
      const file = fileStore.get(item.localId)
      if (!file) {
        patch(item.localId, { error: 'File is no longer in memory — drop it again to retry.', status: 'failed' })
        return
      }
      const displayName = (item.displayName || stemFileName(file.name)).trim()
      if (!displayName) {
        patch(item.localId, { error: 'Give this document a name before uploading.', status: 'queued' })
        return
      }
      patch(item.localId, { status: 'uploading', progress: 5, error: null, displayName })
      try {
        const hash = await sha256Hex(file)
        const reserved = await apiFetch<{
          document_id: string
          upload_url: string
          auth_required?: boolean
          headers: Record<string, string>
        }>('/api/v1/documents/upload-url', {
          method: 'POST',
          body: JSON.stringify({
            filename: file.name,
            display_name: displayName,
            mime_type: file.type || item.mimeType,
            doc_type_hint: asDocTypeHint(item.docType),
            file_size: file.size,
            content_hash: hash,
          }),
        })
        patch(item.localId, { documentId: reserved.document_id, progress: 10 })
        const headers = { ...(reserved.headers ?? {}) }
        if (reserved.auth_required !== false) {
          const token = getAccessToken()
          if (token) headers.Authorization = `Bearer ${token}`
        }
        await putWithProgress(reserved.upload_url, file, headers, (pct) =>
          patch(item.localId, { progress: pct }),
        )
        const status = await apiFetch<HealthDocument>(
          `/api/v1/documents/${reserved.document_id}/complete`,
          { method: 'POST' },
        )
        patch(item.localId, {
          status: status.status,
          stage: status.stage,
          progress: 100,
          needsReview: status.needs_review,
          displayName: status.display_name || displayName,
        })
        startWatching(reserved.document_id)
      } catch (e) {
        patch(item.localId, {
          status: 'failed',
          error: e instanceof Error ? e.message : 'Upload failed',
        })
      }
    },
    [patch, startWatching],
  )

  useEffect(() => {
    const onOnline = () => {
      const failed = useUploadQueueStore.getState().items.filter((i) => i.status === 'failed' && fileStore.has(i.localId))
      failed.forEach((item) => void uploadOne(item))
    }
    window.addEventListener('online', onOnline)
    return () => {
      window.removeEventListener('online', onOnline)
      watchers.current.forEach((stop) => stop())
    }
  }, [uploadOne])

  async function changeDocType(item: QueueItem, docType: DocType | 'auto') {
    patch(item.localId, { docType })
    if (item.documentId && docType !== 'auto') {
      await apiFetch(`/api/v1/documents/${item.documentId}`, {
        method: 'PATCH',
        body: JSON.stringify({ doc_type: docType }),
      })
    }
  }

  async function retry(item: QueueItem) {
    if (item.documentId && item.status === 'failed') {
      try {
        const status = await apiFetch<HealthDocument>(`/api/v1/documents/${item.documentId}/retry`, {
          method: 'POST',
        })
        applyStatus(item.documentId, status)
        startWatching(item.documentId)
        return
      } catch {
        /* re-upload from local file */
      }
    }
    await uploadOne(item)
  }

  const locked = Boolean(gateError) || user?.role !== 'patient'

  return (
    <div className="dashboard">
      <header className="dash-header">
        <div>
          <div className="eyebrow">Documents</div>
          <h1>Upload & ingestion</h1>
          <p className="muted">Status moves Uploaded → Scanning → Extracting → Validating → Ready.</p>
        </div>
      </header>
      {gateError && <p className="form-error">{gateError}</p>}
      <UploadDropzone disabled={locked} />
      <div className="upload-queue">
        {items.map((item) => (
          <UploadQueueItem
            key={item.localId}
            item={item}
            onRetry={retry}
            onStartUpload={(it) => void uploadOne(it)}
            onReview={(it) => it.documentId && setReviewId(it.documentId)}
            onDocType={changeDocType}
          />
        ))}
      </div>
      {reviewId && (
        <ExtractedFieldsReviewTable
          documentId={reviewId}
          onConfirmed={() => {
            applyStatus(reviewId, { status: 'confirmed', needs_review: false, stage: 'Ready' })
            setReviewId(null)
          }}
        />
      )}
    </div>
  )
}
