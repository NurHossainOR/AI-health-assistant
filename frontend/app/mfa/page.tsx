import { AuthGuard } from '@/components/guards/RouteGuards'
import { MfaView } from '@/components/dashboard/DashboardView'

export default function MfaPage() {
  return (
    <AuthGuard>
      <MfaView />
    </AuthGuard>
  )
}
