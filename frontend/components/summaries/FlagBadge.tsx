import { FLAG_LABELS, type LabFlag } from '@/types/trends'

export function FlagBadge({ flag }: { flag?: LabFlag | null }) {
  const value: LabFlag = flag ?? 'unknown'
  return <span className={`badge flag-badge flag-${value}`}>{FLAG_LABELS[value]}</span>
}
