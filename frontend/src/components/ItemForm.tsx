import { useState, type FormEvent } from 'react'
import type { Item } from '../types'

export interface ItemFormValues {
  id: string
  name: string
  description: string
}

interface Props {
  /** Item being edited, or null to create a new one. The parent remounts the form via `key`. */
  editing: Item | null
  disabled: boolean
  onSubmit: (values: ItemFormValues) => Promise<boolean>
  onCancel: () => void
}

export function ItemForm({ editing, disabled, onSubmit, onCancel }: Props) {
  const [id, setId] = useState(editing?.id ?? '')
  const [name, setName] = useState(editing?.name ?? '')
  const [description, setDescription] = useState(editing?.description ?? '')

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const ok = await onSubmit({
      id: id.trim(),
      name: name.trim(),
      description: description.trim(),
    })
    if (ok && editing === null) {
      setId('')
      setName('')
      setDescription('')
    }
  }

  return (
    <form
      className="item-form"
      onSubmit={handleSubmit}
      aria-label={editing ? 'Edit item' : 'Create item'}
    >
      <h2>{editing ? `Edit ${editing.id}` : 'New item'}</h2>

      <label htmlFor="item-id">ID</label>
      <input
        id="item-id"
        name="id"
        value={id}
        onChange={(event) => setId(event.target.value)}
        disabled={disabled || editing !== null}
        required
        maxLength={64}
        autoComplete="off"
      />

      <label htmlFor="item-name">Name</label>
      <input
        id="item-name"
        name="name"
        value={name}
        onChange={(event) => setName(event.target.value)}
        disabled={disabled}
        required
        maxLength={100}
        autoComplete="off"
      />

      <label htmlFor="item-description">Description</label>
      <textarea
        id="item-description"
        name="description"
        value={description}
        onChange={(event) => setDescription(event.target.value)}
        disabled={disabled}
        maxLength={500}
        rows={3}
      />

      <div className="actions">
        <button type="submit" disabled={disabled}>
          {editing ? 'Save' : 'Create'}
        </button>
        {editing !== null && (
          <button type="button" onClick={onCancel} disabled={disabled}>
            Cancel
          </button>
        )}
      </div>
    </form>
  )
}
