import { AuthLayout } from '@/components/layout/AuthLayout'
import { GuestGuard } from '@/components/guards/RouteGuards'
import { LoginForm } from '@/components/auth/LoginForm'

export default function LoginPage() {
  return (
    <GuestGuard>
      <AuthLayout>
        <LoginForm />
      </AuthLayout>
    </GuestGuard>
  )
}
