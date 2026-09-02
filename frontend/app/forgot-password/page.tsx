import { AuthLayout } from '@/components/layout/AuthLayout'
import { GuestGuard } from '@/components/guards/RouteGuards'
import { ForgotPasswordForm } from '@/components/auth/ForgotPasswordForm'

export default function ForgotPasswordPage() {
  return (
    <GuestGuard>
      <AuthLayout>
        <ForgotPasswordForm />
      </AuthLayout>
    </GuestGuard>
  )
}
