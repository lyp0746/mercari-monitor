import React from 'react'
import Dashboard from './pages/Dashboard'
import Keywords from './pages/Keywords'
import Items from './pages/Items'
import Settings from './pages/Settings'
import Watchlist from './pages/Watchlist'
import BlockedItems from './pages/BlockedItems'
import Stats from './pages/Stats'
import Logs from './pages/Logs'
import Login from './pages/Login'
import Orders from './pages/Orders'
import PlatformAccounts from './pages/PlatformAccounts'
import { useWS } from './hooks/useWS'
import { auth, monitor } from './api/client'

const NAV_ITEMS = [
  { path: '/', icon: '🏠', label: '首页' },
  { path: '/items', icon: '🔍', label: '发现' },
  { path: '/keywords', icon: '📡', label: '监控' },
  { path: '/orders', icon: '📦', label: '订单' },
  { path: '/watchlist', icon: '⭐', label: '收藏' },
  { path: '/accounts', icon: '🌐', label: '平台' },
  { path: '/settings', icon: '⚙️', label: '我的' },
]

const MOBILE_NAV = [
  { path: '/', icon: '🏠', label: '首页' },
  { path: '/items', icon: '🔍', label: '发现' },
  { path: '/keywords', icon: '📡', label: '监控' },
  { path: '/orders', icon: '📦', label: '订单' },
  { path: '/settings', icon: '👤', label: '我的' },
]

export default function App() {
  const [route, setRoute] = React.useState(window.location.pathname)
  const [running, setRunning] = React.useState(false)
  const [authed, setAuthed] = React.useState<boolean | null>(null)
  const [newCount, setNewCount] = React.useState(0)
  const [searchQuery, setSearchQuery] = React.useState('')
  const { on } = useWS()

  React.useEffect(() => {
    window.addEventListener('popstate', () => setRoute(window.location.pathname))
    return () => window.removeEventListener('popstate', () => {})
  }, [])

  React.useEffect(() => {
    auth.status().then((s: any) => {
      if (!s.enabled) setAuthed(true)
      else setAuthed(s.logged_in)
    }).catch(() => setAuthed(true))
    fetch('/api/monitor/status').then(r => r.json()).then(s => setRunning(s.running)).catch(() => {})
  }, [])

  React.useEffect(() => {
    const interval = setInterval(() => {
      fetch('/api/monitor/status').then(r => r.json()).then(s => setRunning(s.running)).catch(() => {})
    }, 2000)
    return () => clearInterval(interval)
  }, [])

  React.useEffect(() => {
    const off = on('new_item', () => setNewCount(c => c + 1))
    return off
  }, [on])

  function navigate(path: string) {
    window.history.pushState(null, '', path)
    setRoute(path)
  }

  function handleLogout() {
    auth.logout()
    setAuthed(false)
  }

  async function toggleMonitor() {
    try {
      if (running) {
        await monitor.stop()
        setRunning(false)
      } else {
        await monitor.start()
        setRunning(true)
      }
    } catch {}
  }

  function handleSearch(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'Enter' && searchQuery.trim()) {
      navigate(`/items?keyword=${encodeURIComponent(searchQuery.trim())}`)
    }
  }

  if (authed === null) {
    return <div style={{ minHeight: '100vh', background: 'var(--bg-primary)' }} />
  }

  if (!authed) {
    return <Login onLogin={() => setAuthed(true)} />
  }

  return (
    <>
      <nav className="top-nav">
        <div className="top-nav-brand" onClick={() => navigate('/')}>
          <div className="top-nav-logo">🛒</div>
          <span className="top-nav-title">煤炉助手</span>
        </div>

        <div className="top-nav-links">
          {NAV_ITEMS.map(item => (
            <a
              key={item.path}
              className={`top-nav-link ${route === item.path ? 'active' : ''}`}
              onClick={e => { e.preventDefault(); navigate(item.path) }}
            >
              <span className="link-icon">{item.icon}</span>
              <span>{item.label}</span>
            </a>
          ))}
        </div>

        <div className="top-nav-search">
          <span className="search-icon">🔍</span>
          <input
            placeholder="搜索日本商品、关键词..."
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
            onKeyDown={handleSearch}
          />
        </div>

        <div className="top-nav-right">
          {newCount > 0 && (
            <span className="top-nav-badge" onClick={() => { setNewCount(0); navigate('/items') }}>
              {newCount}
            </span>
          )}
          <button
            className={`monitor-toggle ${running ? 'running' : 'stopped'}`}
            onClick={toggleMonitor}
          >
            <span className={`monitor-dot ${running ? 'on' : 'off'}`} />
            {running ? '监控中' : '已停止'}
          </button>
          <div className="user-menu" onClick={handleLogout}>
            👤 退出
          </div>
        </div>
      </nav>

      <main className="main-content">
        {route === '/' && <Dashboard />}
        {route === '/keywords' && <Keywords />}
        {route === '/items' && <Items />}
        {route === '/watchlist' && <Watchlist />}
        {route === '/blocked' && <BlockedItems />}
        {route === '/stats' && <Stats />}
        {route === '/logs' && <Logs />}
        {route === '/orders' && <Orders />}
        {route === '/accounts' && <PlatformAccounts />}
        {route === '/settings' && <Settings />}
      </main>

      <div className="bottom-nav">
        {MOBILE_NAV.map(item => (
          <div
            key={item.path}
            className={`bottom-nav-item ${route === item.path ? 'active' : ''}`}
            onClick={() => navigate(item.path)}
          >
            <span className="icon">{item.icon}</span>
            <span>{item.label}</span>
          </div>
        ))}
      </div>
    </>
  )
}