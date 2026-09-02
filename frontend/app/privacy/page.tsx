import { AuthGuard } from '@/components/guards/RouteGuards'
import { PrivacyCenter } from '@/components/profile/PrivacyCenter'

export default function PrivacyPage() {
  return (
    <AuthGuard>
      <PrivacyCenter />
    </AuthGuard>
  )
}
