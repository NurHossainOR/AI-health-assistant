import { Suspense } from 'react'
import { AuthGuard, RoleGuard } from '@/components/guards/RouteGuards'
import { AppNav } from '@/components/layout/AppNav'
import { TrendsView } from '@/components/trends/TrendsView'

export default function TrendsPage() {
  return (
    <AuthGuard>
      <RoleGuard roles={['patient', 'doctor', 'caregiver']}>
        <AppNav />
        <Suspense fallback={null}>
          <TrendsView />
        </Suspense>
      </RoleGuard>
    </AuthGuard>
  )
}
