const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1').replace(/\/$/, '')
const DEFAULT_TIMEOUT_MS = 12000

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly requestId?: string,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

function getMessage(raw: string, fallback: string): string {
  if (!raw) return fallback
  try {
    const parsed = JSON.parse(raw) as { detail?: unknown; message?: unknown }
    if (typeof parsed.detail === 'string') return parsed.detail
    if (parsed.detail && typeof parsed.detail === 'object' && 'message' in parsed.detail) {
      const detail = parsed.detail as { message?: unknown }
      if (typeof detail.message === 'string') return detail.message
    }
    if (typeof parsed.message === 'string') return parsed.message
  } catch {
    // Backend returned a non-JSON response.
  }
  return raw.length > 400 ? fallback : raw
}

/** HTTP client with a deadline, normalized errors and cancellation support. */
export async function apiRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  const controller = new AbortController()
  const timeoutMs = init.signal ? DEFAULT_TIMEOUT_MS : DEFAULT_TIMEOUT_MS
  const timeout = setTimeout(() => controller.abort(new DOMException('Tempo limite excedido', 'TimeoutError')), timeoutMs)
  const externalSignal = init.signal
  const abortFromExternal = () => controller.abort(externalSignal?.reason)
  externalSignal?.addEventListener('abort', abortFromExternal, { once: true })

  try {
    const response = await fetch(`${API_BASE_URL}${path.startsWith('/') ? path : `/${path}`}`, {
      ...init,
      signal: controller.signal,
      headers: {
        Accept: 'application/json',
        ...(init.body ? { 'Content-Type': 'application/json' } : {}),
        ...init.headers,
      },
    })

    if (!response.ok) {
      const raw = await response.text().catch(() => '')
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
      throw new ApiError('O servidor respondeu em formato inesperado. Atualize os dados antes de repetir.', response.status)
    }
  } catch (error) {
    if (error instanceof ApiError) throw error
    if (controller.signal.aborted) {
      throw new ApiError(
        externalSignal?.aborted
          ? 'A solicitação foi cancelada.'
          : 'A API não respondeu dentro do prazo. Confira a conexão e atualize os dados antes de repetir a operação.',
        0,
      )
    }
    throw new ApiError('Não foi possível conectar à API. Confira a conexão e tente novamente.', 0)
  } finally {
    clearTimeout(timeout)
    externalSignal?.removeEventListener('abort', abortFromExternal)
  }
}
