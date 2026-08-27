import { AuthGuard, RoleGuard } from '@/components/guards/RouteGuards'
import { AdminConsole } from '@/components/admin/AdminConsole'

export default function AdminPage() {
  return (
    <AuthGuard>
      <RoleGuard roles={['admin']}>
        <AdminConsole />
      </RoleGuard>
    </AuthGuard>
  )
}
