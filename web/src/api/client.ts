const API_BASE = '/api'

function getToken(): string | null {
  return localStorage.getItem('auth_token')
}

export async function api<T>(path: string, options?: RequestInit): Promise<T> {
  const token = getToken()
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...((options?.headers as Record<string, string>) || {}),
  }
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || `请求失败 (${res.status})`)
  }
  return res.json()
}

export const keywords = {
  list: (platform?: string) => api<any>('/keywords' + (platform ? `?platform=${platform}` : '')),
  add: (data: any) => api('/keywords', { method: 'POST', body: JSON.stringify(data) }),
  update: (id: number, data: any) => api(`/keywords/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  delete: (id: number) => api(`/keywords/${id}`, { method: 'DELETE' }),
  toggle: (id: number, enabled: boolean) =>
    api(`/keywords/${id}/toggle`, { method: 'PUT', body: JSON.stringify({ enabled }) }),
}

export const items = {
  list: (params?: Record<string, any>) => {
    const q = new URLSearchParams(params || {}).toString()
    return api<any>(`/items${q ? '?' + q : ''}`)
  },
  stats: () => api<any>('/items/stats'),
  platformStats: () => api<any>('/items/platform-stats'),
}

export const monitor = {
  start: () => api('/monitor/start', { method: 'POST' }),
  stop: () => api('/monitor/stop', { method: 'POST' }),
  status: () => api('/monitor/status'),
}

export const settings = {
  get: () => api('/settings'),
  update: (data: any) => api('/settings', { method: 'PUT', body: JSON.stringify(data) }),
  testTelegram: () => api('/settings/test-telegram', { method: 'POST' }),
}

export const auth = {
  status: () => api<any>('/auth/status'),
  login: (username: string, password: string) =>
    api<any>('/auth/login', { method: 'POST', body: JSON.stringify({ username, password }) }),
  register: (username: string, password: string) =>
    api<any>('/auth/register', { method: 'POST', body: JSON.stringify({ username, password }) }),
  logout: () => { localStorage.removeItem('auth_token'); localStorage.removeItem('auth_user') },
}

export const watchlist = {
  listSellers: () => api<any>('/watchlist/sellers'),
  addSeller: (data: any) => api('/watchlist/sellers', { method: 'POST', body: JSON.stringify(data) }),
  removeSeller: (sellerId: string, platform: string) =>
    api(`/watchlist/sellers/${sellerId}/${platform}`, { method: 'DELETE' }),
  listItems: () => api<any>('/watchlist/items'),
  addItem: (data: any) => api('/watchlist/items', { method: 'POST', body: JSON.stringify(data) }),
  removeItem: (itemId: string, platform: string) =>
    api(`/watchlist/items/${itemId}/${platform}`, { method: 'DELETE' }),
}

export const blocked = {
  list: () => api<any>('/blocked'),
  add: (itemId: string, platform: string, reason: string = '') =>
    api('/blocked', { method: 'POST', body: JSON.stringify({ item_id: itemId, platform, reason }) }),
  remove: (itemId: string, platform: string) =>
    api(`/blocked/${encodeURIComponent(itemId)}/${platform}`, { method: 'DELETE' }),
}

export const orderApi = {
  list: (params?: Record<string, any>) => {
    const q = new URLSearchParams(params || {}).toString()
    return api<any>(`/orders${q ? '?' + q : ''}`)
  },
  create: (data: any) => api('/orders', { method: 'POST', body: JSON.stringify(data) }),
  update: (id: number, data: any) => api(`/orders/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  delete: (id: number) => api(`/orders/${id}`, { method: 'DELETE' }),
  getByItem: (itemId: string, platform: string) =>
    api<any>(`/orders/item/${encodeURIComponent(itemId)}/${platform}`),
  statusFlow: () => api<any>('/orders/status-flow'),
}

export const itemDetail = {
  get: (itemId: string, platform: string) =>
    api<any>(`/item-detail/${encodeURIComponent(itemId)}/${platform}`),
}

export const accounts = {
  list: (platform?: string) =>
    api<any>('/accounts' + (platform ? `?platform=${platform}` : '')),
  add: (data: any) => api('/accounts', { method: 'POST', body: JSON.stringify(data) }),
  get: (id: number) => api<any>(`/accounts/${id}`),
  remove: (id: number) => api(`/accounts/${id}`, { method: 'DELETE' }),
}