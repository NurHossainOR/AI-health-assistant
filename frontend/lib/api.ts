const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? ''

let accessToken: string | null = null

export function getAccessToken() {
  return accessToken
}

export function setAccessToken(token: string | null) {
  accessToken = token
}

export class ApiError extends Error {
  status: number
  code?: string

  constructor(message: string, status: number, code?: string) {
    super(message)
    this.status = status
    this.code = code
  }
}

async function parseJson(res: Response) {
  const text = await res.text()
  if (!text) return null
  try {
    return JSON.parse(text)
  } catch {
    return { detail: text }
  }
}

export async function apiFetch<T>(
  path: string,
  options: RequestInit = {},
  retry = true,
): Promise<T> {
  const headers = new Headers(options.headers)
  if (!headers.has('Content-Type') && options.body) {
    headers.set('Content-Type', 'application/json')
  }
  if (accessToken) {
    headers.set('Authorization', `Bearer ${accessToken}`)
  }

  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
    credentials: 'include',
  })

  if (res.status === 401 && retry && path !== '/api/v1/auth/refresh') {
    try {
      const refreshed = await apiFetch<{ access_token: string }>(
        '/api/v1/auth/refresh',
        { method: 'POST', body: JSON.stringify({}) },
        false,
      )
      setAccessToken(refreshed.access_token)
      return apiFetch<T>(path, options, false)
    } catch {
      setAccessToken(null)
    }
  }

  const data = await parseJson(res)
  if (!res.ok) {
    throw new ApiError(
      data?.detail ?? 'Request failed',
      res.status,
      data?.code,
    )
  }
  return data as T
}
