import React, { useEffect, useState } from 'react'
import { items } from '../api/client'

interface PlatformStat {
  platform: string
  total: number
  today: number
}

const PLATFORM_INFO: Record<string, { name: string; flag: string; color: string }> = {
  mercari_jp: { name: '煤炉', flag: '🇯🇵', color: '#ff4d6a' },
  mercarijp: { name: '煤炉', flag: '🇯🇵', color: '#ff4d6a' },
  mercari: { name: '煤炉', flag: '🇯🇵', color: '#ff4d6a' },
  yahoo_auctions: { name: 'Yahoo拍卖', flag: '🇯🇵', color: '#ff6600' },
  yahoo: { name: 'Yahoo拍卖', flag: '🇯🇵', color: '#ff6600' },
  surugaya: { name: '駿河屋', flag: '🇯🇵', color: '#8b5cf6' },
  rakuten: { name: '楽天', flag: '🇯🇵', color: '#bf0000' },
  yahoo_shopping: { name: 'Yahoo购物', flag: '🇯🇵', color: '#ff8c00' },
  paypay_fleamarket: { name: 'PayPay', flag: '🇯🇵', color: '#ff0033' },
  paypay: { name: 'PayPay', flag: '🇯🇵', color: '#ff0033' },
  fril: { name: 'Rakuma', flag: '🇯🇵', color: '#e6007e' },
  rakuma: { name: 'Rakuma', flag: '🇯🇵', color: '#e6007e' },
  bunjang: { name: '번장', flag: '🇰🇷', color: '#3c8cff' },
  carousell: { name: 'Carousell', flag: '🌏', color: '#00b5ad' },
}

export default function Stats() {
  const [stats, setStats] = useState<PlatformStat[]>([])
  const [totals, setTotals] = useState({ total: 0, today: 0 })

  useEffect(() => {
    const load = () => {
      items.stats().then((s: any) => {
        setTotals({ total: s.total, today: s.today })
      })
      items.platformStats().then((p: PlatformStat[]) => {
        setStats(p || [])
      })
    }
    load()
    const t = setInterval(load, 10000)
    return () => clearInterval(t)
  }, [])

  const maxVal = Math.max(...stats.map(s => s.total), 1)

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1 className="page-title">📊 数据统计</h1>
          <p className="page-subtitle">监控数据概览和平台分布</p>
        </div>
      </div>

      <div className="stat-grid">
        <div className="stat-card">
          <div className="stat-label">总商品数</div>
          <div className="stat-value" style={{ color: 'var(--accent-primary)' }}>{totals.total}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">今日新增</div>
          <div className="stat-value" style={{ color: 'var(--success)' }}>{totals.today}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">监控平台</div>
          <div className="stat-value" style={{ color: 'var(--info)' }}>{stats.length}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">今日占比</div>
          <div className="stat-value" style={{ color: 'var(--warning)' }}>
            {totals.total > 0 ? ((totals.today / totals.total) * 100).toFixed(1) : 0}%
          </div>
        </div>
      </div>

      <div className="card">
        <div className="section-header">
          <div className="section-title">📈 各平台商品分布</div>
        </div>
        {stats.length === 0 ? (
          <div className="empty">
            <div className="empty-icon">📊</div>
            <div className="empty-title">暂无数据</div>
          </div>
        ) : (
          <div className="chart-bars">
            {stats.map(s => {
              const info = PLATFORM_INFO[s.platform] || { name: s.platform, flag: '📦', color: '#999' }
              return (
                <div key={s.platform} className="chart-row">
                  <span className="chart-label">
                    {info.flag} {info.name}
                  </span>
                  <div className="chart-bar-wrap">
                    <div
                      className="chart-bar"
                      style={{
                        width: `${(s.total / maxVal) * 100}%`,
                        background: info.color,
                      }}
                    >
                      <span className="chart-bar-total">{s.total}</span>
                    </div>
                    {s.today > 0 && (
                      <div
                        className="chart-bar chart-bar-today"
                        style={{
                          width: `${(s.today / maxVal) * 100}%`,
                          background: info.color + '66',
                        }}
                      />
                    )}
                  </div>
                  <span className="chart-val">
                    <span className="tag tag-success" style={{ fontSize: 10 }}>+{s.today}</span>
                    <span style={{ marginLeft: 6 }}>{s.total}</span>
                  </span>
                </div>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}