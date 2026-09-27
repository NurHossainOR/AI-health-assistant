import { AuthGuard, RoleGuard } from '@/components/guards/RouteGuards'
import { AppNav } from '@/components/layout/AppNav'
import { ChatWindow } from '@/components/chat/ChatWindow'

export default function ChatPage() {
  return (
    <AuthGuard>
      <RoleGuard roles={['patient']}>
        <AppNav />
        <ChatWindow />
      </RoleGuard>
    </AuthGuard>
  )
}
