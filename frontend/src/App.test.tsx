import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import type { Item } from './types'

/** Tiny in-memory implementation of the backend REST contract, mounted on global fetch. */
function createFakeBackend() {
  const store = new Map<string, Item>()

  const respond = (status: number, body?: unknown): Response =>
    ({
      ok: status >= 200 && status < 300,
      status,
      json: async () => {
        if (body === undefined) throw new SyntaxError('empty body')
        return body
      },
    }) as unknown as Response

  const fetchImpl = vi.fn(
    async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
      const url = new URL(String(input), 'http://frontend.test')
      const method = init?.method ?? 'GET'
      const match = /^\/api\/items(?:\/([^/]+))?$/.exec(url.pathname)
      if (!match) return respond(404, { detail: 'not found' })
      const id = match[1] ? decodeURIComponent(match[1]) : undefined
      const now = new Date().toISOString()

      if (id === undefined && method === 'GET') {
        const page = Number(url.searchParams.get('page') ?? '1')
        const size = Number(url.searchParams.get('page_size') ?? '20')
        const all = [...store.values()]
        return respond(200, {
          items: all.slice((page - 1) * size, page * size),
          page,
          page_size: size,
          total: all.length,
        })
      }
      if (id === undefined && method === 'POST') {
        const body = JSON.parse(String(init?.body)) as {
          id: string
          name: string
          description: string
        }
        if (store.has(body.id)) {
          return respond(409, { detail: 'item with this id already exists' })
        }
        const item: Item = { ...body, created_at: now, updated_at: now }
        store.set(item.id, item)
        return respond(201, item)
      }
      if (id !== undefined && method === 'GET') {
        const item = store.get(id)
        return item ? respond(200, item) : respond(404, { detail: 'item not found' })
      }
      if (id !== undefined && method === 'PUT') {
        const item = store.get(id)
        if (!item) return respond(404, { detail: 'item not found' })
        const body = JSON.parse(String(init?.body)) as { name: string; description: string }
        const updated: Item = { ...item, ...body, updated_at: now }
        store.set(id, updated)
        return respond(200, updated)
      }
      if (id !== undefined && method === 'DELETE') {
        return store.delete(id) ? respond(204) : respond(404, { detail: 'item not found' })
      }
      return respond(405, { detail: 'method not allowed' })
    },
  )

  return { store, fetchImpl }
}

describe('App CRUD flow', () => {
  let backend: ReturnType<typeof createFakeBackend>

  beforeEach(() => {
    backend = createFakeBackend()
    vi.stubGlobal('fetch', backend.fetchImpl)
    vi.spyOn(window, 'confirm').mockReturnValue(true)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('creates, edits and deletes an item through relative /api calls', async () => {
    const user = userEvent.setup()
    render(<App />)

    expect(await screen.findByText('No items yet.')).toBeInTheDocument()

    // create
    await user.type(screen.getByLabelText('ID'), 'phase2-smoke-001')
    await user.type(screen.getByLabelText('Name'), 'Keyboard')
    await user.type(screen.getByLabelText('Description'), 'Mechanical keyboard')
    await user.click(screen.getByRole('button', { name: 'Create' }))

    const row = await screen.findByTestId('item-row-phase2-smoke-001')
    expect(within(row).getByText('Keyboard')).toBeInTheDocument()
    expect(within(row).getByText('Mechanical keyboard')).toBeInTheDocument()
    expect(backend.store.get('phase2-smoke-001')?.description).toBe('Mechanical keyboard')
    expect(screen.getByLabelText('ID')).toHaveValue('') // form reset after a successful create

    // update
    await user.click(within(row).getByRole('button', { name: 'Edit phase2-smoke-001' }))
    expect(screen.getByLabelText('ID')).toBeDisabled()
    const nameInput = screen.getByLabelText('Name')
    await user.clear(nameInput)
    await user.type(nameInput, 'Keyboard v2')
    await user.click(screen.getByRole('button', { name: 'Save' }))

    expect(await screen.findByText('Keyboard v2')).toBeInTheDocument()
    expect(backend.store.get('phase2-smoke-001')?.name).toBe('Keyboard v2')
    expect(screen.getByRole('button', { name: 'Create' })).toBeInTheDocument() // back to create

    // delete
    await user.click(screen.getByRole('button', { name: 'Delete phase2-smoke-001' }))

    expect(await screen.findByText('No items yet.')).toBeInTheDocument()
    expect(backend.store.size).toBe(0)

    // every request went to a relative /api path: no scheme, host or port in the bundle
    expect(backend.fetchImpl).toHaveBeenCalled()
    for (const [input] of backend.fetchImpl.mock.calls) {
      expect(String(input)).toMatch(/^\/api\//)
    }
  })

  it('shows the backend error when creating a duplicate id', async () => {
    const user = userEvent.setup()
    const now = new Date().toISOString()
    backend.store.set('dup-1', {
      id: 'dup-1',
      name: 'Existing',
      description: '',
      created_at: now,
      updated_at: now,
    })
    render(<App />)

    expect(await screen.findByText('Existing')).toBeInTheDocument()

    await user.type(screen.getByLabelText('ID'), 'dup-1')
    await user.type(screen.getByLabelText('Name'), 'Again')
    await user.click(screen.getByRole('button', { name: 'Create' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      '409: item with this id already exists',
    )
    expect(backend.store.get('dup-1')?.name).toBe('Existing')
  })
})
