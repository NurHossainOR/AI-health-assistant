'use client'

import { useT } from '@/lib/i18n'
import type { LabFlag } from '@/types/trends'

export function FlagBadge({ flag }: { flag?: LabFlag | null }) {
  const t = useT()
  const value: LabFlag = flag ?? 'unknown'
  return <span className={`badge flag-badge flag-${value}`}>{t(`flag.${value}`)}</span>
}
