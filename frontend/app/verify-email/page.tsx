import { Suspense } from 'react'
import { VerifyEmailForm } from '@/components/auth/VerifyEmailForm'

export default function VerifyEmailPage() {
  return (
    <Suspense fallback={<p className="loading">Loading…</p>}>
      <VerifyEmailForm />
    </Suspense>
  )
}
