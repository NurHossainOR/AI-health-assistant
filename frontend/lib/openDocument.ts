import { apiFetchBlob } from '@/lib/api'

/** Fetch the original file with auth and open it in a new tab (download if the popup is blocked). */
export async function openDocumentFile(documentId: string) {
  const { blob, filename } = await apiFetchBlob(`/api/v1/documents/${documentId}/file`)
  const url = URL.createObjectURL(blob)
  const opened = window.open(url, '_blank', 'noopener,noreferrer')
  if (!opened) {
    const a = document.createElement('a')
    a.href = url
    a.target = '_blank'
    a.rel = 'noopener noreferrer'
    if (!blob.type.startsWith('image/') && blob.type !== 'application/pdf') {
      a.download = filename || 'document'
    }
    a.click()
  }
  window.setTimeout(() => URL.revokeObjectURL(url), 60_000)
}
