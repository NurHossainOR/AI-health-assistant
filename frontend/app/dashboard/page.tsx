import { AuthGuard } from '@/components/guards/RouteGuards'
import { DashboardView } from '@/components/dashboard/DashboardView'

export default function DashboardPage() {
  return (
    <AuthGuard>
      <DashboardView />
    </AuthGuard>
  )
}
