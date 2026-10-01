import React, { useEffect, useState } from 'react'
import { items, monitor } from '../api/client'
import { useWS } from '../hooks/useWS'
import ItemCard from '../components/ItemCard'
import LogPanel from '../components/LogPanel'
import { PLATFORM_NAMES } from '../constants'

const CATEGORIES = [
  { id: 'all', icon: '🏪', name: '全部' },
  { id: 'anime', icon: '🎌', name: '动漫周边' },
  { id: 'figure', icon: '🎭', name: '模玩手办' },
  { id: 'vintage', icon: '📿', name: '中古好物' },
  { id: 'outdoor', icon: '🏕️', name: '户外装备' },
  { id: 'game', icon: '🎮', name: '游戏掌机' },
  { id: 'fashion', icon: '👘', name: '服饰杂货' },
  { id: 'beauty', icon: '💄', name: '美妆护肤' },
]

const PLATFORM_FILTERS = [
  { id: '', flag: '🌍', name: '全部平台' },
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

export default function Dashboard() {
  const [stats, setStats] = useState<any>(null)
  const [status, setStatus] = useState<any>(null)
  const [recentItems, setRecentItems] = useState<any[]>([])
  const [logs, setLogs] = useState<string[]>([])
  const [platformFilter, setPlatformFilter] = useState<string>('')
  const [sessionNew, setSessionNew] = useState(0)
  const [page, setPage] = useState(1)
  const [hasMore, setHasMore] = useState(true)
  const [activeCategory, setActiveCategory] = useState('all')

  const { connected, on } = useWS()

  const loadItems = (p: number, filter: string) => {
    const params: any = { limit: 12, offset: (p - 1) * 12 }
    if (filter) params.platform = filter
    items.list(params).then(d => {
      if (p === 1) setRecentItems(d.items)
      else setRecentItems(prev => [...prev, ...d.items])
      setHasMore(d.items.length === 12)
    })
  }

  useEffect(() => {
    const fetchData = () => {
      items.stats().then(setStats)
      monitor.status().then(setStatus)
    }
    fetchData()
    loadItems(1, platformFilter)
    const interval = setInterval(fetchData, 5000)
    return () => clearInterval(interval)
  }, [])

  useEffect(() => {
    setPage(1)
    loadItems(1, platformFilter)
  }, [platformFilter])

  useEffect(() => {
    const off1 = on('new_item', (item: any) => {
      if (!platformFilter || item.platform === platformFilter) {
        setRecentItems(prev => [item, ...prev].slice(0, 60))
      }
      setLogs(prev => [...prev, `[${new Date().toLocaleTimeString()}] 新商品: ${item.name}`].slice(-200))
      setSessionNew(c => c + 1)
      setStats((s: any) => s ? { ...s, total: s.total + 1, today: s.today + 1 } : s)
    })
    const off2 = on('log', (data: any) => {
      setLogs(prev => [...prev, `[${new Date().toLocaleTimeString()}] [${data.platform}] ${data.message}`].slice(-200))
    })
    return () => { off1(); off2() }
  }, [on, stats, platformFilter])

  const platforms = [...new Set(recentItems.map(i => i.platform).filter(Boolean))] as string[]

  function handleLoadMore() {
    const next = page + 1
    setPage(next)
    loadItems(next, platformFilter)
  }

  return (
    <div className="page">
      <div className="hero-section">
        <div className="hero-title">🇯🇵 日本好物，一键直达</div>
        <div className="hero-subtitle">
          实时监控煤炉、雅虎拍卖、PayPay等日本平台，新品上架秒级推送，降价自动提醒
        </div>
        <div className="hero-stats">
          <div className="hero-stat">
            <div className="hero-stat-val">{stats?.total ?? 0}</div>
            <div className="hero-stat-label">总商品</div>
          </div>
          <div className="hero-stat">
            <div className="hero-stat-val">{stats?.today ?? 0}</div>
            <div className="hero-stat-label">今日发现</div>
          </div>
          <div className="hero-stat">
            <div className="hero-stat-val">{sessionNew}</div>
            <div className="hero-stat-label">本次发现</div>
          </div>
          <div className="hero-stat">
            <div className="hero-stat-val">{status?.platforms?.length ?? 0}</div>
            <div className="hero-stat-label">运行平台</div>
          </div>
        </div>
      </div>

      <div className="category-grid">
        {CATEGORIES.map(cat => (
          <div
            key={cat.id}
            className={`category-card ${activeCategory === cat.id ? 'active' : ''}`}
            onClick={() => setActiveCategory(cat.id)}
          >
            <span className="category-icon">{cat.icon}</span>
            <span className="category-name">{cat.name}</span>
          </div>
        ))}
      </div>

      <div className="dash-grid">
        <section>
          <div className="section-header">
            <div className="section-title">🔥 最新上架</div>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              <span style={{ fontSize: 12, color: connected ? 'var(--success)' : 'var(--text-muted)' }}>
                {connected ? '● 实时' : '○ 离线'}
              </span>
              <button className="btn btn-sm btn-ghost" onClick={() => { setRecentItems([]); setSessionNew(0) }}>
                清空
              </button>
            </div>
          </div>

          <div className="platform-tabs">
            {PLATFORM_FILTERS.map(p => (
              <button
                key={p.id}
                className={`platform-tab ${platformFilter === p.id ? 'active' : ''}`}
                onClick={() => setPlatformFilter(platformFilter === p.id ? '' : p.id)}
              >
                <span className="tab-flag">{p.flag}</span>
                {p.name}
              </button>
            ))}
          </div>

          <div className="item-grid">
            {recentItems.map((item, i) => (
              <ItemCard key={`${item.item_id}-${i}`} item={item} />
            ))}
          </div>

          {recentItems.length === 0 && (
            <div className="empty">
              <div className="empty-icon">🛍️</div>
              <div className="empty-title">暂无商品</div>
              <div style={{ color: 'var(--text-muted)', fontSize: 13 }}>启动监控后自动刷新商品</div>
            </div>
          )}

          {hasMore && recentItems.length > 0 && (
            <div style={{ textAlign: 'center', marginTop: 20 }}>
              <button className="btn btn-outline" onClick={handleLoadMore}>加载更多</button>
            </div>
          )}
        </section>

        <aside>
          <LogPanel logs={logs} />

          <div className="platform-status">
            <h4>📡 平台状态</h4>
            {(status?.platforms || []).map((p: any) => (
              <div key={p.platform} className="p-row">
                <span>{p.name}</span>
                <span className={`p-stat ${p.running ? 'on' : ''}`}>
                  第{p.stats?.cycles || 0}轮 · 匹配{p.stats?.matched || 0}
                </span>
              </div>
            ))}
          </div>
        </aside>
      </div>
    </div>
  )
}