'use client'

import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { DocType, DocumentStatus, HealthDocument } from '@/types/documents'

export interface QueueItem {
  localId: string
  documentId?: string
  fileName: string
  displayName: string
  mimeType: string
  size: number
  docType: DocType | 'auto'
  status: DocumentStatus | 'queued' | 'uploading'
  progress: number
  error?: string | null
  stage?: string
  needsReview?: boolean
}

interface UploadQueueState {
  items: QueueItem[]
  upsert: (item: QueueItem) => void
  patch: (localId: string, patch: Partial<QueueItem>) => void
  remove: (localId: string) => void
  applyStatus: (documentId: string, doc: Partial<HealthDocument> & { stage?: string }) => void
}

export const fileStore = new Map<string, File>()

export const useUploadQueueStore = create<UploadQueueState>()(
  persist(
    (set) => ({
      items: [],
      upsert: (item) =>
        set((s) => {
          const idx = s.items.findIndex((i) => i.localId === item.localId)
          if (idx === -1) return { items: [...s.items, item] }
          const next = [...s.items]
          next[idx] = { ...next[idx], ...item }
          return { items: next }
        }),
      patch: (localId, patch) =>
        set((s) => ({
          items: s.items.map((i) => (i.localId === localId ? { ...i, ...patch } : i)),
        })),
      remove: (localId) =>
        set((s) => ({ items: s.items.filter((i) => i.localId !== localId) })),
      applyStatus: (documentId, doc) =>
        set((s) => ({
          items: s.items.map((i) =>
            i.documentId === documentId
              ? {
                  ...i,
                  status: (doc.status as QueueItem['status']) ?? i.status,
                  stage: doc.stage ?? i.stage,
                  error: doc.error_message ?? i.error,
                  needsReview: doc.needs_review ?? i.needsReview,
                  displayName: doc.display_name ?? i.displayName,
                }
              : i,
          ),
        })),
    }),
    { name: 'spondon-upload-queue' },
  ),
)
