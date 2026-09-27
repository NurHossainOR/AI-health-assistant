import { AuthGuard } from '@/components/guards/RouteGuards'
import { AppNav } from '@/components/layout/AppNav'
import { DocumentDetail } from '@/components/documents/DocumentDetail'

export default function DocumentPage() {
  return (
    <AuthGuard>
      <AppNav />
      <DocumentDetail />
    </AuthGuard>
  )
}
