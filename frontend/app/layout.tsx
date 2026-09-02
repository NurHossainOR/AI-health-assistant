import type { Metadata } from 'next'
import { AppProviders } from '@/components/providers/AppProviders'
import './globals.css'

export const metadata: Metadata = {
  title: 'Spondon — Every result, understood.',
  description: 'Upload any blood test, scan, or discharge summary. Spondon reads it, tracks it against your history, and explains exactly what changed.',
  icons: {
    icon: '/favicon.svg',
  },
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body suppressHydrationWarning>
        <AppProviders>{children}</AppProviders>
      </body>
    </html>
  )
}
