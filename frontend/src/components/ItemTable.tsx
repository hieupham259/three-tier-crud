import type { Item } from '../types'

interface Props {
  items: Item[]
  disabled: boolean
  onEdit: (item: Item) => void
  onDelete: (item: Item) => void
}

export function ItemTable({ items, disabled, onEdit, onDelete }: Props) {
  if (items.length === 0) {
    return <p className="empty">No items yet.</p>
  }

  return (
    <table className="items">
      <thead>
        <tr>
          <th scope="col">ID</th>
          <th scope="col">Name</th>
          <th scope="col">Description</th>
          <th scope="col">Updated</th>
          <th scope="col">
            <span className="visually-hidden">Actions</span>
          </th>
        </tr>
      </thead>
      <tbody>
        {items.map((item) => (
          <tr key={item.id} data-testid={`item-row-${item.id}`}>
            <td>
              <code>{item.id}</code>
            </td>
            <td>{item.name}</td>
            <td>{item.description}</td>
            <td>{new Date(item.updated_at).toLocaleString()}</td>
            <td className="row-actions">
              <button
                type="button"
                onClick={() => onEdit(item)}
                disabled={disabled}
                aria-label={`Edit ${item.id}`}
              >
                Edit
              </button>
              <button
                type="button"
                onClick={() => onDelete(item)}
                disabled={disabled}
                aria-label={`Delete ${item.id}`}
              >
                Delete
              </button>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}
