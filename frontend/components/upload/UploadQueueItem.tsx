'use client'

import { DOC_TYPE_LABELS, documentShareLabel, stemFileName, type DocType } from '@/types/documents'
import { useUploadQueueStore, type QueueItem } from '@/lib/uploadQueue'

const CHIP: Record<string, string> = {
  queued: 'badge-pending',
  uploading: 'badge-pending',
  awaiting_upload: 'badge-pending',
  uploaded: 'badge-normal',
  pending: 'badge-normal',
  scanning: 'badge-pending',
  extracting: 'badge-pending',
  validating: 'badge-pending',
  retrying: 'badge-pending',
  needs_review: 'badge-watch',
  extracted: 'badge-normal',
  confirmed: 'badge-normal',
  failed: 'badge-watch',
}

export function UploadQueueItem({
  item,
  onRetry,
  onReview,
  onDocType,
  onStartUpload,
}: {
  item: QueueItem
  onRetry: (item: QueueItem) => void
  onReview: (item: QueueItem) => void
  onDocType: (item: QueueItem, docType: DocType | 'auto') => void
  onStartUpload: (item: QueueItem) => void
}) {
  const patch = useUploadQueueStore((s) => s.patch)
  const remove = useUploadQueueStore((s) => s.remove)
  const displayName = (item.displayName || stemFileName(item.fileName)).trim()
  const label = item.stage || item.status.replaceAll('_', ' ')
  const heading = documentShareLabel(displayName)
  const canUpload = item.status === 'queued' && displayName.length > 0

  return (
    <div className="upload-queue-item">
      <div className="upload-queue-meta">
        <strong>{heading}</strong>
        <span className={`badge ${CHIP[item.status] ?? 'badge-pending'}`}>{label}</span>
      </div>
      <p className="muted" style={{ fontSize: '13px', margin: '0 0 8px' }}>
        File: {item.fileName}
      </p>
      {item.status === 'queued' && (
        <label>
          Document name
          <input
            value={item.displayName !== undefined ? item.displayName : stemFileName(item.fileName)}
            onChange={(e) => patch(item.localId, { displayName: e.target.value })}
            placeholder="e.g. CBC panel"
            maxLength={255}
          />
        </label>
      )}
      <div className="upload-queue-row">
        <label>
          Document type
          <select
            value={item.docType}
            onChange={(e) => onDocType(item, e.target.value as DocType | 'auto')}
          >
            {(Object.keys(DOC_TYPE_LABELS) as Array<DocType | 'auto'>).map((k) => (
              <option key={k} value={k}>
                {DOC_TYPE_LABELS[k]}
              </option>
            ))}
          </select>
        </label>
      </div>
      <div className="progress-track" aria-hidden>
        <div className="progress-fill" style={{ width: `${Math.min(100, item.progress)}%` }} />
      </div>
      {item.error && <p className="form-error">{item.error}</p>}
      <div className="upload-queue-actions">
        {item.status === 'queued' && (
          <button
            type="button"
            className="btn btn-primary"
            style={{ width: 'auto' }}
            disabled={!canUpload}
            onClick={() => onStartUpload({ ...item, displayName })}
          >
            Upload
          </button>
        )}
        {item.needsReview && (
          <button type="button" className="btn btn-teal" style={{ width: 'auto' }} onClick={() => onReview(item)}>
            Review fields
          </button>
        )}
        {item.status === 'failed' && (
          <button type="button" className="btn btn-ghost" style={{ width: 'auto' }} onClick={() => onRetry(item)}>
            Retry
          </button>
        )}
        <button type="button" className="btn btn-ghost" style={{ width: 'auto' }} onClick={() => remove(item.localId)}>
          Dismiss
        </button>
      </div>
    </div>
  )
}
