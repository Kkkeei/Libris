const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1').replace(/\/$/, '')

export class ApiError extends Error {
  constructor(message: string, public readonly status: number) { super(message); this.name = 'ApiError' }
}

/** Cliente HTTP centralizado. Requer uma API FastAPI disponível para chamadas reais. */
export async function apiRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path.startsWith('/') ? path : `/${path}`}`, {
    ...init,
    headers: { Accept: 'application/json', ...(init.body ? { 'Content-Type': 'application/json' } : {}), ...init.headers },
  })
  if (!response.ok) {
    const raw = await response.text().catch(() => '')
    let message = raw
    try { const parsed = JSON.parse(raw) as { detail?: unknown; message?: string }; message = typeof parsed.detail === 'string' ? parsed.detail : typeof parsed.message === 'string' ? parsed.message : raw } catch { /* response was not JSON */ }
    throw new ApiError(message || `A solicitação falhou (${response.status}).`, response.status)
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}
