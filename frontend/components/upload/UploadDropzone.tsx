'use client'

import { useCallback } from 'react'
import { useDropzone } from 'react-dropzone'
import { fileStore, useUploadQueueStore } from '@/lib/uploadQueue'
import type { DocType } from '@/types/documents'
import { stemFileName } from '@/types/documents'

const ACCEPT = {
  'application/pdf': ['.pdf'],
  'image/jpeg': ['.jpg', '.jpeg'],
  'image/png': ['.png'],
  'application/dicom': ['.dcm'],
  'application/octet-stream': ['.dcm'],
}

function newLocalId() {
  return crypto.randomUUID()
}

export function UploadDropzone({
  onFilesAdded,
  disabled,
}: {
  onFilesAdded?: (localIds: string[]) => void
  disabled?: boolean
}) {
  const upsert = useUploadQueueStore((s) => s.upsert)

  const onDrop = useCallback(
    (accepted: File[]) => {
      const ids: string[] = []
      for (const file of accepted) {
        const localId = newLocalId()
        fileStore.set(localId, file)
        upsert({
          localId,
          fileName: file.name,
          displayName: stemFileName(file.name),
          mimeType: file.type || guessMime(file.name),
          size: file.size,
          docType: 'auto',
          status: 'queued',
          progress: 0,
        })
        ids.push(localId)
      }
      if (ids.length) onFilesAdded?.(ids)
    },
    [onFilesAdded, upsert],
  )

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: ACCEPT,
    multiple: true,
    disabled,
    maxSize: 25 * 1024 * 1024,
  })

  return (
    <div
      {...getRootProps()}
      className={`upload-dropzone ${isDragActive ? 'active' : ''} ${disabled ? 'disabled' : ''}`}
    >
      <input {...getInputProps()} />
      <p className="eyebrow" style={{ justifyContent: 'center' }}>
        Upload center
      </p>
      <h2 style={{ marginTop: '12px' }}>Drop reports here</h2>
      <p className="muted">
        PDF, JPG, PNG, or DICOM · up to 25MB each. Queue several files and walk away — processing
        continues in the background.
      </p>
      <button type="button" className="btn btn-primary" disabled={disabled} style={{ marginTop: '18px', width: 'auto' }}>
        Choose files
      </button>
    </div>
  )
}

export function guessMime(name: string) {
  const ext = name.split('.').pop()?.toLowerCase()
  if (ext === 'pdf') return 'application/pdf'
  if (ext === 'png') return 'image/png'
  if (ext === 'jpg' || ext === 'jpeg') return 'image/jpeg'
  if (ext === 'dcm') return 'application/dicom'
  return 'application/octet-stream'
}

export function asDocTypeHint(value: DocType | 'auto') {
  return value === 'auto' ? 'auto' : value
}
