import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  API_BASE,
  ApiError,
  createItem,
  deleteItem,
  getItem,
  listItems,
  updateItem,
} from './client'
import type { Item } from '../types'

const ITEM: Item = {
  id: 'phase2-smoke-001',
  name: 'Keyboard',
  description: 'Mechanical keyboard',
  created_at: '2026-09-06T10:00:00Z',
  updated_at: '2026-09-06T10:00:00Z',
}

function jsonResponse(status: number, body?: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => {
      if (body === undefined) throw new SyntaxError('empty body')
      return body
    },
  } as unknown as Response
}

const fetchMock = vi.fn<typeof fetch>()

function lastCall(): { url: string; init: RequestInit | undefined } {
  const call = fetchMock.mock.calls.at(-1)
  if (!call) throw new Error('fetch was not called')
  return { url: String(call[0]), init: call[1] }
}

describe('api client', () => {
  beforeEach(() => {
    fetchMock.mockReset()
    vi.stubGlobal('fetch', fetchMock)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('uses a relative /api base so the bundle never embeds a backend host', () => {
    expect(API_BASE).toBe('/api')
  })

  it('lists items with pagination query parameters', async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(200, { items: [ITEM], page: 2, page_size: 5, total: 6 }),
    )

    const page = await listItems(2, 5)

    expect(page.total).toBe(6)
    expect(page.items[0]).toEqual(ITEM)
    const { url, init } = lastCall()
    expect(url).toBe('/api/items?page=2&page_size=5')
    expect(init?.method).toBe('GET')
    expect(init?.body).toBeUndefined()
  })

  it('creates an item with a JSON body', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(201, ITEM))

    await expect(
      createItem({ id: ITEM.id, name: ITEM.name, description: ITEM.description }),
    ).resolves.toEqual(ITEM)

    const { url, init } = lastCall()
    expect(url).toBe('/api/items')
    expect(init?.method).toBe('POST')
    expect((init?.headers as Record<string, string>)['Content-Type']).toBe('application/json')
    expect(JSON.parse(String(init?.body))).toEqual({
      id: ITEM.id,
      name: ITEM.name,
      description: ITEM.description,
    })
  })

  it('encodes the id in the path', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(200, ITEM))

    await getItem('a b/c')

    expect(lastCall().url).toBe('/api/items/a%20b%2Fc')
  })

  it('sends only name and description on update', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(200, { ...ITEM, name: 'Keyboard v2' }))

    const updated = await updateItem(ITEM.id, {
      name: 'Keyboard v2',
      description: ITEM.description,
    })

    expect(updated.name).toBe('Keyboard v2')
    const { url, init } = lastCall()
    expect(url).toBe(`/api/items/${ITEM.id}`)
    expect(init?.method).toBe('PUT')
    expect(JSON.parse(String(init?.body))).toEqual({
      name: 'Keyboard v2',
      description: ITEM.description,
    })
  })

  it('treats 204 as success for delete', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(204))

    await expect(deleteItem(ITEM.id)).resolves.toBeUndefined()

    const { url, init } = lastCall()
    expect(url).toBe(`/api/items/${ITEM.id}`)
    expect(init?.method).toBe('DELETE')
  })

  it('throws ApiError carrying the backend detail on 404', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(404, { detail: 'item not found' }))

    const error = await getItem('missing').catch((err: unknown) => err)

    expect(error).toBeInstanceOf(ApiError)
    expect((error as ApiError).status).toBe(404)
    expect((error as ApiError).message).toBe('item not found')
  })

  it('throws ApiError on 409 conflicts', async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(409, { detail: 'item with this id already exists' }),
    )

    await expect(createItem({ id: 'dup', name: 'Dup', description: '' })).rejects.toMatchObject({
      status: 409,
      message: 'item with this id already exists',
    })
  })

  it('flattens FastAPI validation errors (422) into one message', async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(422, {
        detail: [
          { loc: ['body', 'name'], msg: 'String should have at least 1 character' },
          { loc: ['body', 'id'], msg: 'String should match pattern' },
        ],
      }),
    )

    await expect(createItem({ id: 'bad id', name: '', description: '' })).rejects.toMatchObject({
      status: 422,
      message: 'name: String should have at least 1 character; id: String should match pattern',
    })
  })

  it('falls back to a generic message when the error body is not JSON', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(502))

    await expect(listItems()).rejects.toMatchObject({
      status: 502,
      message: 'Request failed with status 502',
    })
  })

  it('wraps network failures in ApiError with status 0', async () => {
    fetchMock.mockRejectedValueOnce(new TypeError('Failed to fetch'))

    await expect(getItem('x')).rejects.toMatchObject({ status: 0, message: 'Failed to fetch' })
  })
})
