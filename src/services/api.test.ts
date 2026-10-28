import { afterEach, describe, expect, it, vi } from 'vitest'
import { apiRequest, ApiError } from './api'

afterEach(() => {
  vi.unstubAllGlobals()
  vi.useRealTimers()
  vi.restoreAllMocks()
})

describe('apiRequest', () => {
  it('returns parsed JSON after a successful response', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ status: 'ok' }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      ),
    )

    await expect(apiRequest<{ status: string }>('/health')).resolves.toEqual({ status: 'ok' })
  })

  it('preserves the HTTP status and readable backend message', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail: 'Este exemplar já está emprestado.' }), {
          status: 409,
          headers: { 'Content-Type': 'application/json', 'X-Request-ID': 'req-test-1' },
        }),
      ),
    )

    await expect(apiRequest('/loans')).rejects.toMatchObject({
      name: 'ApiError',
      status: 409,
      requestId: 'req-test-1',
      message: 'Este exemplar já está emprestado.',
    })
  })

  it('returns a recoverable timeout error when the API does not respond', async () => {
    vi.useFakeTimers()
    vi.stubGlobal(
      'fetch',
      vi.fn((_input: RequestInfo | URL, init?: RequestInit) => new Promise<Response>((_resolve, reject) => {
        init?.signal?.addEventListener(
          'abort',
          () => reject(new DOMException('The request was aborted', 'AbortError')),
          { once: true },
        )
      })),
    )

    const pending = apiRequest('/slow')
    await vi.advanceTimersByTimeAsync(12_000)
    await expect(pending).rejects.toMatchObject({
      name: 'ApiError',
      status: 0,
      message: expect.stringContaining('12 segundos'),
    })
  })

  it('normalizes a network error instead of leaving the caller waiting', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('network failure')))

    await expect(apiRequest('/health')).rejects.toMatchObject({
      name: 'ApiError',
      status: 0,
      message: expect.stringContaining('conectar à API'),
    })
  })
})
