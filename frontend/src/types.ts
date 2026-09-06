export interface Item {
  id: string
  name: string
  description: string
  created_at: string
  updated_at: string
}

export interface ItemCreate {
  id: string
  name: string
  description: string
}

export interface ItemUpdate {
  name: string
  description: string
}

export interface ItemPage {
  items: Item[]
  page: number
  page_size: number
  total: number
}
