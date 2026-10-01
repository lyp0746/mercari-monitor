import React, { useEffect, useState, useCallback } from 'react'
import { blocked } from '../api/client'

const PLATFORM_NAMES: Record<string, string> = {
  mercari_jp: '煤炉', bunjang: 'Bunjang', paypay_fleamarket: 'PayPay',
  fril: 'Rakuma', yahoo_auctions: 'Yahoo拍卖', carousell: 'Carousell',
  surugaya: '駿河屋', rakuten: '楽天', yahoo_shopping: 'Yahoo购物',
}

const PLATFORM_FLAGS: Record<string, string> = {
  mercari_jp: '🇯🇵', bunjang: '🇰🇷', paypay_fleamarket: '🇯🇵',
  fril: '🇯🇵', yahoo_auctions: '🇯🇵', carousell: '🌏',
  surugaya: '🇯🇵', rakuten: '🇯🇵', yahoo_shopping: '🇯🇵',
}

export default function BlockedItems() {
  const [data, setData] = useState<{ items: any[]; total: number }>({ items: [], total: 0 })
  const [loading, setLoading] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const d = await blocked.list()
      setData(d)
    } catch (err) {
      console.error('加载屏蔽列表失败:', err)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const handleRemove = async (itemId: string, platform: string) => {
    try {
      await blocked.remove(itemId, platform)
      setData(prev => ({
        ...prev,
        items: prev.items.filter((i: any) => !(i.item_id === itemId && i.platform === platform)),
        total: prev.total - 1,
      }))
    } catch (err) {
      console.error('取消屏蔽失败:', err)
    }
  }

  const formatDate = (d: string) => {
    if (!d) return ''
    try {
      return new Date(d).toLocaleString('zh-CN')
    } catch {
      return d
    }
  }

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1 className="page-title">🚫 屏蔽列表</h1>
          <p className="page-subtitle">被屏蔽的商品不再出现在监控通知中</p>
        </div>
        <span className="tag">{data.total} 条</span>
      </div>

      {loading && (
        <div style={{ textAlign: 'center', padding: 20 }}>
          <span className="spinner" /> 加载中...
        </div>
      )}

      {!loading && data.items.length === 0 && (
        <div className="empty">
          <div className="empty-icon">🚫</div>
          <div className="empty-title">暂无屏蔽商品</div>
          <div style={{ color: 'var(--text-muted)', fontSize: 13 }}>屏蔽的商品将不会推送通知</div>
        </div>
      )}

      <div className="blocked-list">
        {data.items.map((item: any, i: number) => (
          <div key={`${item.item_id}-${item.platform}-${i}`} className="card blocked-row">
            <div className="blocked-info">
              <div className="blocked-id">{item.item_id}</div>
              <div className="blocked-meta">
                <span className="tag tag-accent">
                  {PLATFORM_FLAGS[item.platform] || '📦'} {PLATFORM_NAMES[item.platform] || item.platform}
                </span>
                {item.reason && <span className="tag tag-warning">{item.reason}</span>}
                <span className="blocked-time">{formatDate(item.created_at)}</span>
              </div>
            </div>
            <button className="btn btn-outline btn-sm"
                    onClick={() => handleRemove(item.item_id, item.platform)}>
              取消屏蔽
            </button>
          </div>
        ))}
      </div>
    </div>
  )
}