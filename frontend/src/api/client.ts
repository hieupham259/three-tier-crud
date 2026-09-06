import type { Item, ItemCreate, ItemPage, ItemUpdate } from '../types'

/**
 * Every request is relative to the page origin. In Kubernetes nginx proxies /api/ to the
 * backend Service, so the bundle never needs (and never contains) a backend host or port.
 */
export const API_BASE = '/api'

export class ApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

interface ValidationIssue {
  loc?: Array<string | number>
  msg?: string
}

interface ErrorBody {
  detail?: string | ValidationIssue[]
}

interface RequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'DELETE'
  body?: unknown
}

function messageFromBody(status: number, body: unknown): string {
  if (body !== null && typeof body === 'object' && 'detail' in body) {
    const detail = (body as ErrorBody).detail
    if (typeof detail === 'string') return detail
    if (Array.isArray(detail)) {
      const parts = detail.map((issue) => {
        const where = (issue.loc ?? []).filter((part) => part !== 'body').join('.')
        const msg = issue.msg ?? 'invalid value'
        return where ? `${where}: ${msg}` : msg
      })
      if (parts.length > 0) return parts.join('; ')
    }
  }
  return `Request failed with status ${status}`
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const headers: Record<string, string> = { Accept: 'application/json' }
  const init: RequestInit = { method: options.method ?? 'GET', headers }
  if (options.body !== undefined) {
    headers['Content-Type'] = 'application/json'
    init.body = JSON.stringify(options.body)
  }

  let response: Response
  try {
    response = await fetch(`${API_BASE}${path}`, init)
  } catch (error) {
    throw new ApiError(0, error instanceof Error ? error.message : 'Network error')
  }

  if (response.status === 204) return undefined as unknown as T

  let body: unknown = null
  try {
    body = await response.json()
  } catch {
    body = null
  }
  if (!response.ok) throw new ApiError(response.status, messageFromBody(response.status, body))
  return body as T
}

export function listItems(page = 1, pageSize = 20): Promise<ItemPage> {
  const query = new URLSearchParams({ page: String(page), page_size: String(pageSize) })
  return request<ItemPage>(`/items?${query.toString()}`)
}

export function getItem(id: string): Promise<Item> {
  return request<Item>(`/items/${encodeURIComponent(id)}`)
}

export function createItem(input: ItemCreate): Promise<Item> {
  return request<Item>('/items', { method: 'POST', body: input })
}

export function updateItem(id: string, input: ItemUpdate): Promise<Item> {
  return request<Item>(`/items/${encodeURIComponent(id)}`, { method: 'PUT', body: input })
}

export async function deleteItem(id: string): Promise<void> {
  await request<void>(`/items/${encodeURIComponent(id)}`, { method: 'DELETE' })
}
