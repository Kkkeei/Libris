const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1').replace(/\/$/, '')
const DEFAULT_TIMEOUT_MS = 12000
const TOKEN_KEY = 'libris.access_token'

export class ApiError extends Error {
  constructor(message: string, public readonly status: number, public readonly requestId?: string) {
    super(message)
    this.name = 'ApiError'
  }
}

function getMessage(raw: string, fallback: string): string {
  if (!raw) return fallback
  try {
    const parsed = JSON.parse(raw) as { detail?: unknown; message?: unknown }
    if (typeof parsed.detail === 'string') return parsed.detail
    if (typeof parsed.message === 'string') return parsed.message
  } catch {
    // Non-JSON response.
  }
  return raw.length <= 400 ? raw : fallback
}

export async function apiRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), DEFAULT_TIMEOUT_MS)
  const externalSignal = init.signal
  const abortFromExternal = () => controller.abort()
  externalSignal?.addEventListener('abort', abortFromExternal, { once: true })

  try {
    const token = typeof sessionStorage === 'undefined' ? null : sessionStorage.getItem(TOKEN_KEY)
    const headers = new Headers(init.headers)
    headers.set('Accept', 'application/json')
    if (init.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json')
    if (token && !headers.has('Authorization')) headers.set('Authorization', `Bearer ${token}`)
    const response = await fetch(`${API_BASE_URL}${path.startsWith('/') ? path : `/${path}`}`, {
      ...init,
      signal: controller.signal,
      headers,
    })
    if (!response.ok) {
      const raw = await response.text().catch(() => '')
      if (response.status === 401 && typeof sessionStorage !== 'undefined') {
        sessionStorage.removeItem(TOKEN_KEY)
        sessionStorage.removeItem('libris.role')
        sessionStorage.removeItem('libris.display_name')
        if (typeof window !== 'undefined') window.dispatchEvent(new Event('libris-session-expired'))
      }
      throw new ApiError(
        getMessage(raw, `A solicitação falhou (HTTP ${response.status}).`),
        response.status,
        response.headers.get('X-Request-ID') || undefined,
      )
    }
    if (response.status === 204) return undefined as T
    try {
      return await response.json() as T
    } catch {
      throw new ApiError('A resposta do servidor foi inválida. Atualize os dados antes de tentar novamente.', response.status)
    }
  } catch (error) {
    if (error instanceof ApiError) throw error
    if (controller.signal.aborted) {
      throw new ApiError(
        externalSignal?.aborted ? 'Solicitação cancelada.' : 'A API não respondeu em 12 segundos. Confira a conexão e atualize os dados antes de repetir a operação.',
        0,
      )
    }
    throw new ApiError('Não foi possível conectar à API. Confira a conexão e tente novamente.', 0)
  } finally {
    clearTimeout(timeout)
    externalSignal?.removeEventListener('abort', abortFromExternal)
  }
}
