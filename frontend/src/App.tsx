import { useCallback, useEffect, useState } from 'react'
import { API_BASE, ApiError, createItem, deleteItem, listItems, updateItem } from './api/client'
import { ItemForm, type ItemFormValues } from './components/ItemForm'
import { ItemTable } from './components/ItemTable'
import type { Item } from './types'

const PAGE_SIZE = 10

function describeError(error: unknown): string {
  if (error instanceof ApiError) {
    return error.status > 0 ? `${error.status}: ${error.message}` : error.message
  }
  return error instanceof Error ? error.message : 'Unexpected error'
}

export default function App() {
  const [items, setItems] = useState<Item[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [editing, setEditing] = useState<Item | null>(null)

  const load = useCallback(async (targetPage: number) => {
    setLoading(true)
    try {
      const result = await listItems(targetPage, PAGE_SIZE)
      if (result.items.length === 0 && targetPage > 1) {
        setPage(targetPage - 1) // the last item of this page was deleted: step back one page
        return
      }
      setItems(result.items)
      setTotal(result.total)
      setError(null)
    } catch (err) {
      setError(describeError(err))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load(page)
  }, [load, page])

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))

  async function handleSubmit(values: ItemFormValues): Promise<boolean> {
    setBusy(true)
    try {
      if (editing) {
        await updateItem(editing.id, { name: values.name, description: values.description })
        setEditing(null)
      } else {
        await createItem(values)
      }
      setError(null)
      await load(page)
      return true
    } catch (err) {
      setError(describeError(err))
      return false
    } finally {
      setBusy(false)
    }
  }

  async function handleDelete(item: Item) {
    if (!window.confirm(`Delete item "${item.id}"?`)) return
    setBusy(true)
    try {
      await deleteItem(item.id)
      if (editing?.id === item.id) setEditing(null)
      setError(null)
      await load(page)
    } catch (err) {
      setError(describeError(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <main className="app">
      <header>
        <h1>Three-tier CRUD</h1>
        <p className="muted">
          React + FastAPI + MongoDB. API base: <code>{API_BASE}</code>
        </p>
      </header>

      {error && (
        <div role="alert" className="error">
          {error}
        </div>
      )}

      <section className="layout">
        <ItemForm
          key={editing?.id ?? 'new'}
          editing={editing}
          disabled={busy}
          onSubmit={handleSubmit}
          onCancel={() => setEditing(null)}
        />

        <section aria-label="Items" aria-busy={loading}>
          <div className="toolbar">
            <span>{total} item(s)</span>
            <button
              type="button"
              onClick={() => setPage((current) => current - 1)}
              disabled={page <= 1 || loading}
            >
              Previous
            </button>
            <span>
              Page {page} / {totalPages}
            </span>
            <button
              type="button"
              onClick={() => setPage((current) => current + 1)}
              disabled={page >= totalPages || loading}
            >
              Next
            </button>
            <button type="button" onClick={() => void load(page)} disabled={loading}>
              Refresh
            </button>
          </div>
          {loading ? (
            <p>Loading…</p>
          ) : (
            <ItemTable items={items} disabled={busy} onEdit={setEditing} onDelete={handleDelete} />
          )}
        </section>
      </section>
    </main>
  )
}
