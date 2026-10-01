import React, { useEffect, useState } from 'react'
import { keywords, items } from '../api/client'
import { PLATFORM_NAMES } from '../constants'

const NAV = [
  { path: '/', icon: '📊', label: '仪表盘' },
  { path: '/keywords', icon: '🔍', label: '关键词' },
  { path: '/items', icon: '📦', label: '商品流' },
  { path: '/watchlist', icon: '⭐', label: '关注列表' },
  { path: '/stats', icon: '📈', label: '统计' },
  { path: '/logs', icon: '📋', label: '日志' },
  { path: '/blocked', icon: '🚫', label: '屏蔽管理' },
  { path: '/settings', icon: '⚙️', label: '设置' },
]

export default function Sidebar({
  running, onLogout, onNavigate, username,
}: {
  running: boolean; onLogout?: () => void; onNavigate?: (path: string) => void; username?: string
}) {
  const currentPath = window.location.pathname
  const [platformStats, setPlatformStats] = useState<Record<string, number>>({})
  const [quickKw, setQuickKw] = useState('')
  const [quickPlat, setQuickPlat] = useState('mercari')

  useEffect(() => {
    const load = () => {
      items.platformStats().then((stats: any[]) => {
        const map: Record<string, number> = {}
        stats?.forEach((s: any) => { map[s.platform] = s.total })
        setPlatformStats(map)
      })
    }
    load()
    const t = setInterval(load, 30000)
    return () => clearInterval(t)
  }, [])

  async function handleQuickAdd() {
    const kw = quickKw.trim()
    if (!kw) return
    try {
      await keywords.add({ keyword: kw, platform: quickPlat, enabled: true })
      setQuickKw('')
    } catch {}
  }

  function handleNav(e: React.MouseEvent, path: string) {
    e.preventDefault()
    if (onNavigate) {
      onNavigate(path)
    } else {
      window.history.pushState(null, '', path)
      window.dispatchEvent(new PopStateEvent('popstate'))
    }
  }

  const activePlatforms = Object.keys(platformStats).filter(p => platformStats[p] > 0)

  return (
    <aside className="sidebar">
      <div className="brand">
        <div className="brand-logo">🛒</div>
        <div>
          <div className="brand-text">二手监控</div>
          <div className="brand-subtitle">实时多平台上新</div>
        </div>
      </div>

      <nav className="nav">
        {NAV.map(item => {
          const active = currentPath === item.path
          return (
            <a key={item.path} href={item.path}
               className={`nav-item ${active ? 'active' : ''}`}
               onClick={e => handleNav(e, item.path)}>
              <span className="icon">{item.icon}</span>
              <span>{item.label}</span>
            </a>
          )
        })}
      </nav>

      <div className="nav-section-label">快速添加关键词</div>
      <div className="quick-add">
        <select
          className="quick-add-select"
          value={quickPlat}
          onChange={e => setQuickPlat(e.target.value)}
        >
          {Object.entries(PLATFORM_NAMES).map(([k, v]) => (
            <option key={k} value={k}>{v}</option>
          ))}
        </select>
        <input
          className="quick-add-input"
          placeholder="关键词..."
          value={quickKw}
          onChange={e => setQuickKw(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter') handleQuickAdd() }}
        />
        <button className="btn btn-sm btn-primary" onClick={handleQuickAdd}>+</button>
      </div>

      {activePlatforms.length > 0 && (
        <>
          <div className="nav-section-label">平台商品数</div>
          <div className="platform-status">
            {activePlatforms.map(p => (
              <div key={p} className="platform-row">
                <span className="platform-dot" />
                <span className="platform-name">{PLATFORM_NAMES[p] || p}</span>
                <span className="platform-count">{platformStats[p]}</span>
              </div>
            ))}
          </div>
        </>
      )}

      <div style={{ flex: 1 }} />

      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        {username && (
          <div className="user-chip">
            <span>👤</span>
            <span>{username}</span>
          </div>
        )}
        <div className="row" style={{ gap: 6, padding: '6px 10px' }}>
          <span style={{
            width: 8, height: 8, borderRadius: '50%',
            background: running ? 'var(--success)' : 'var(--text-muted)',
            animation: running ? 'pulse-dot 2s infinite' : 'none',
          }} />
          <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
            {running ? '监控运行中' : '已停止'}
          </span>
        </div>
        {onLogout && (
          <button onClick={onLogout}
                  className="btn btn-outline"
                  style={{
                    width: '100%',
                    fontWeight: 600,
                    color: 'var(--text-secondary)',
                    borderColor: 'var(--border)',
                    padding: '9px 18px'
                  }}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.borderColor = 'var(--accent-primary)'
                    e.currentTarget.style.color = 'var(--accent-primary)'
                    e.currentTarget.style.background = 'var(--accent-dim)'
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.borderColor = 'var(--border)'
                    e.currentTarget.style.color = 'var(--text-secondary)'
                    e.currentTarget.style.background = 'transparent'
                  }}>
            退出登录
          </button>
        )}
      </div>
    </aside>
  )
}