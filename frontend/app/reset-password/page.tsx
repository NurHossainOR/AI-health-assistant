import { Suspense } from 'react'
import { AuthLayout } from '@/components/layout/AuthLayout'
import { ResetPasswordForm } from '@/components/auth/ResetPasswordForm'

export default function ResetPasswordPage() {
  return (
    <AuthLayout>
      <Suspense fallback={<p className="loading">Loading…</p>}>
        <ResetPasswordForm />
      </Suspense>
    </AuthLayout>
  )
}
