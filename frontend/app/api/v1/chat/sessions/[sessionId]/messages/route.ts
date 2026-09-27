export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

const backend = process.env.API_PROXY_TARGET ?? 'http://127.0.0.1:8000'

function targetUrl(sessionId: string) {
  return `${backend}/api/v1/chat/sessions/${sessionId}/messages`
}

function forwardHeaders(req: Request) {
  const headers = new Headers()
  const auth = req.headers.get('authorization')
  const cookie = req.headers.get('cookie')
  const contentType = req.headers.get('content-type')
  if (auth) headers.set('Authorization', auth)
  if (cookie) headers.set('Cookie', cookie)
  if (contentType) headers.set('Content-Type', contentType)
  return headers
}

export async function GET(
  req: Request,
  { params }: { params: Promise<{ sessionId: string }> },
) {
  const { sessionId } = await params
  const res = await fetch(targetUrl(sessionId), {
    headers: forwardHeaders(req),
    cache: 'no-store',
  })
  return new Response(res.body, {
    status: res.status,
    headers: {
      'Content-Type': res.headers.get('Content-Type') ?? 'application/json',
    },
  })
}

export async function POST(
  req: Request,
  { params }: { params: Promise<{ sessionId: string }> },
) {
  const { sessionId } = await params
  const res = await fetch(targetUrl(sessionId), {
    method: 'POST',
    headers: forwardHeaders(req),
    body: await req.text(),
    cache: 'no-store',
  })
  return new Response(res.body, {
    status: res.status,
    headers: {
      'Content-Type': res.headers.get('Content-Type') ?? 'text/event-stream',
      'Cache-Control': 'no-cache, no-transform',
      Connection: 'keep-alive',
      'X-Accel-Buffering': 'no',
    },
  })
}
