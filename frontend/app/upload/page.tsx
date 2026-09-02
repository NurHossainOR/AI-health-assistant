import { AuthGuard, RoleGuard } from '@/components/guards/RouteGuards'
import { AppNav } from '@/components/layout/AppNav'
import { UploadCenter } from '@/components/upload/UploadCenter'

export default function UploadPage() {
  return (
    <AuthGuard>
      <RoleGuard roles={['patient']}>
        <AppNav />
        <UploadCenter />
      </RoleGuard>
    </AuthGuard>
  )
}
