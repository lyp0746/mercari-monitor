import React, { useEffect, useState, useCallback } from 'react'
import { items } from '../api/client'
import { useWS } from '../hooks/useWS'
import ItemCard from '../components/ItemCard'

const PLATFORM_FILTERS = [
  { id: '', flag: '🌍', name: '全部' },
  { id: 'mercari_jp', flag: '🇯🇵', name: '煤炉' },
  { id: 'yahoo_auctions', flag: '🇯🇵', name: '雅虎拍卖' },
  { id: 'surugaya', flag: '🇯🇵', name: '駿河屋' },
  { id: 'rakuten', flag: '🇯🇵', name: '楽天' },
  { id: 'yahoo_shopping', flag: '🇯🇵', name: 'Yahoo购物' },
  { id: 'paypay_fleamarket', flag: '🇯🇵', name: 'PayPay' },
  { id: 'fril', flag: '🇯🇵', name: 'Rakuma' },
  { id: 'bunjang', flag: '🇰🇷', name: '번장' },
  { id: 'carousell', flag: '🌏', name: 'Carousell' },
]

const SORT_OPTIONS = [
  { value: 'newest', label: '最新上架' },
  { value: 'price_asc', label: '价格从低到高' },
  { value: 'price_desc', label: '价格从高到低' },
]

export default function Items() {
  const [data, setData] = useState<{ items: any[]; total: number }>({ items: [], total: 0 })
  const [filter, setFilter] = useState('')
  const [platform, setPlatform] = useState('')
  const [sort, setSort] = useState('newest')
  const [page, setPage] = useState(0)
  const pageSize = 24

  const { on, connected } = useWS()

  const load = useCallback(async () => {
    const d = await items.list({
      keyword: filter || undefined,
      platform: platform || undefined,
      limit: pageSize,
      offset: page * pageSize,
    })
    setData(d)
  }, [filter, platform, page])

  useEffect(() => { load() }, [load])

  useEffect(() => {
    const interval = setInterval(load, 10000)
    return () => clearInterval(interval)
  }, [load])

  useEffect(() => {
    const off = on('new_item', (item: any) => {
      setData(prev => ({ ...prev, items: [item, ...prev.items.slice(0, -1)], total: prev.total + 1 }))
    })
    return off
  }, [on])

  const sortedItems = React.useMemo(() => {
    const list = [...data.items]
    switch (sort) {
      case 'price_asc':
        return list.sort((a, b) => (a.price || 0) - (b.price || 0))
      case 'price_desc':
        return list.sort((a, b) => (b.price || 0) - (a.price || 0))
      default:
        return list
    }
  }, [data.items, sort])

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1 className="page-title">🔍 发现好物</h1>
          <p className="page-subtitle">浏览所有监控到的商品，支持搜索和筛选</p>
        </div>
        <div className="items-total-badge">
          共 <strong>{data.total}</strong> 件商品
          <span className={`ws-dot ${connected ? 'on' : 'off'}`}>
            {connected ? '● 实时' : '○ 离线'}
          </span>
        </div>
      </div>

      <div className="items-toolbar">
        <div className="items-search">
          <span className="items-search-icon">🔍</span>
          <input
            type="text"
            placeholder="搜索商品名称、关键词..."
            value={filter}
            onChange={e => { setFilter(e.target.value); setPage(0) }}
            className="items-search-input"
          />
          {filter && (
            <button className="items-search-clear" onClick={() => { setFilter(''); setPage(0) }}>
              ✕
            </button>
          )}
        </div>

        <div className="items-filter-bar">
          <div className="platform-tabs">
            {PLATFORM_FILTERS.map(p => (
              <button
                key={p.id}
                className={`platform-tab ${platform === p.id ? 'active' : ''}`}
                onClick={() => { setPlatform(platform === p.id ? '' : p.id); setPage(0) }}
              >
                <span className="tab-flag">{p.flag}</span>
                {p.name}
              </button>
            ))}
          </div>

          <div className="items-sort">
            <select
              value={sort}
              onChange={e => setSort(e.target.value)}
              className="items-sort-select"
            >
              {SORT_OPTIONS.map(o => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
          </div>
        </div>
      </div>

      <div className="item-grid">
        {sortedItems.map((item, i) => (
          <ItemCard key={`${item.item_id}-${i}-${page}`} item={item} />
        ))}
      </div>

      {data.items.length === 0 && (
        <div className="empty">
          <div className="empty-icon">🛍️</div>
          <div className="empty-title">暂无商品</div>
          <div style={{ color: 'var(--text-muted)', fontSize: 13 }}>启动监控后自动发现商品</div>
        </div>
      )}

      {data.total > pageSize && (
        <div className="pagination">
          <button className="btn btn-outline" disabled={page <= 0} onClick={() => setPage(p => p - 1)}>
            ← 上一页
          </button>
          <span>{page + 1} / {Math.ceil(data.total / pageSize)}</span>
          <button className="btn btn-outline"
                  disabled={(page + 1) * pageSize >= data.total}
                  onClick={() => setPage(p => p + 1)}>
            下一页 →
          </button>
        </div>
      )}
    </div>
  )
}