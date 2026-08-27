import { AuthLayout } from '@/components/layout/AuthLayout'
import { GuestGuard } from '@/components/guards/RouteGuards'
import { SignupForm } from '@/components/auth/SignupForm'

export default function SignupPage() {
  return (
    <GuestGuard>
      <AuthLayout>
        <SignupForm />
      </AuthLayout>
    </GuestGuard>
  )
}
