import { Suspense } from 'react'
import { AuthGuard, RoleGuard } from '@/components/guards/RouteGuards'
import { ProcessingConsentView } from '@/components/profile/ProcessingConsentView'

export default function ProcessingConsentPage() {
  return (
    <AuthGuard>
      <RoleGuard roles={['patient']}>
        <Suspense fallback={<p className="loading">Loading…</p>}>
          <ProcessingConsentView />
        </Suspense>
      </RoleGuard>
    </AuthGuard>
  )
}
