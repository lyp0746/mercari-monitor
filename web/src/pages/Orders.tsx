import React, { useEffect, useState } from 'react'
import { orderApi } from '../api/client'

const STATUS_LABELS: Record<string, string> = {
  pending: '待确认', confirmed: '已确认', purchasing: '代购中',
  purchased: '已购买', shipped_domestic: '日本国内已发货',
  at_warehouse: '已到仓库', shipped_intl: '国际物流中',
  delivered: '已签收', failed: '购买失败', cancelled: '已取消',
}

const STATUS_COLORS: Record<string, string> = {
  pending: '#f59e0b', confirmed: '#3b82f6', purchasing: '#8b5cf6',
  purchased: '#10b981', shipped_domestic: '#06b6d4',
  at_warehouse: '#0ea5e9', shipped_intl: '#6366f1',
  delivered: '#22c55e', failed: '#ef4444', cancelled: '#6b7280',
}

const STATUS_ICONS: Record<string, string> = {
  pending: '⏳', confirmed: '✅', purchasing: '🛒',
  purchased: '📦', shipped_domestic: '🚚',
  at_warehouse: '🏭', shipped_intl: '✈️',
  delivered: '📬', failed: '❌', cancelled: '🚫',
}

const PLATFORM_EMOJI: Record<string, string> = {
  mercari_jp: '🇯🇵', bunjang: '🇰🇷', paypay_fleamarket: '🇯🇵',
  fril: '🇯🇵', yahoo_auctions: '🇯🇵', carousell: '🌏',
  surugaya: '🇯🇵', rakuten: '🇯🇵', yahoo_shopping: '🇯🇵',
}

const CURRENCY: Record<string, string> = {
  JPY: '¥', KRW: '₩', SGD: 'S$', HKD: 'HK$',
  TWD: 'NT$', MYR: 'RM', AUD: 'A$', PHP: '₱',
}

const FILTER_TABS = [
  { key: '', label: '全部' },
  { key: 'pending', label: '⏳ 待确认' },
  { key: 'confirmed', label: '✅ 已确认' },
  { key: 'purchasing', label: '🛒 代购中' },
  { key: 'purchased', label: '📦 已购买' },
  { key: 'shipped_domestic', label: '🚚 国内发货' },
  { key: 'at_warehouse', label: '🏭 已到仓' },
  { key: 'shipped_intl', label: '✈️ 国际物流' },
  { key: 'delivered', label: '📬 已签收' },
  { key: 'failed', label: '❌ 失败' },
  { key: 'cancelled', label: '🚫 已取消' },
]

export default function Orders() {
  const [orders, setOrders] = useState<any[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState('')
  const [statusFlow, setStatusFlow] = useState<any>(null)

  const fetchOrders = async (status?: string) => {
    setLoading(true)
    try {
      const params: Record<string, string> = { limit: '100' }
      if (status) params.status = status
      const res = await orderApi.list(params)
      setOrders(res.items || [])
      setTotal(res.total || 0)
    } catch (err) {
      console.error('获取订单失败:', err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchOrders(filter || undefined)
    orderApi.statusFlow().then(setStatusFlow).catch(() => {})
  }, [filter])

  const handleStatusUpdate = async (orderId: number, newStatus: string) => {
    try {
      await orderApi.update(orderId, { status: newStatus })
      fetchOrders(filter || undefined)
    } catch (err) {
      console.error('更新状态失败:', err)
    }
  }

  const handleDelete = async (orderId: number) => {
    if (!confirm('确定删除此订单？')) return
    try {
      await orderApi.delete(orderId)
      fetchOrders(filter || undefined)
    } catch (err) {
      console.error('删除失败:', err)
    }
  }

  return (
    <div className="page-container">
      <div className="page-header">
        <div>
          <h1 className="page-title">📦 我的订单</h1>
          <p className="page-subtitle">管理代购/代拍订单，追踪物流状态</p>
        </div>
        <div className="page-header-stats">
          <span className="stat-badge">{total} 个订单</span>
        </div>
      </div>

      <div className="order-filter-tabs">
        {FILTER_TABS.map(tab => (
          <button
            key={tab.key}
            className={`order-filter-tab ${filter === tab.key ? 'active' : ''}`}
            onClick={() => setFilter(tab.key)}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="loading-state">
          <span className="spinner" /> 加载中...
        </div>
      ) : orders.length === 0 ? (
        <div className="empty-state">
          <div className="empty-icon">📦</div>
          <div className="empty-text">
            {filter ? '该状态下暂无订单' : '暂无订单，去首页发现好物吧！'}
          </div>
        </div>
      ) : (
        <div className="orders-list">
          {orders.map(order => {
            const emoji = PLATFORM_EMOJI[order.platform] || '📦'
            const sym = CURRENCY[order.currency] || ''
            const nextStatuses = statusFlow?.flow?.[order.status]?.next || []

            return (
              <div key={order.id} className="order-card">
                <div className="order-card-header">
                  <div className="order-card-left">
                    {order.image_url ? (
                      <img src={order.image_url} alt="" className="order-card-img" />
                    ) : (
                      <div className="order-card-img-placeholder">{emoji}</div>
                    )}
                    <div className="order-card-info">
                      <div className="order-card-name">{order.item_name || order.item_id}</div>
                      <div className="order-card-platform">
                        {emoji} {order.platform_name}
                        {order.order_type === 'bid' && ' · 代拍'}
                        {order.order_type === 'buy' && ' · 代购'}
                      </div>
                    </div>
                  </div>
                  <div className="order-card-right">
                    <span
                      className="order-status-badge"
                      style={{ background: STATUS_COLORS[order.status] || '#6b7280' }}
                    >
                      {STATUS_ICONS[order.status] || ''} {STATUS_LABELS[order.status] || order.status}
                    </span>
                  </div>
                </div>

                <div className="order-card-body">
                  <div className="order-card-prices">
                    <div className="order-price-row">
                      <span>商品价格</span>
                      <span>{sym}{order.price?.toLocaleString()}</span>
                    </div>
                    <div className="order-price-row">
                      <span>折合人民币</span>
                      <span>¥{order.cny_price?.toLocaleString()}</span>
                    </div>
                    <div className="order-price-row">
                      <span>服务费 (8%)</span>
                      <span>¥{order.service_fee?.toLocaleString()}</span>
                    </div>
                    <div className="order-price-row">
                      <span>日本国内运费</span>
                      <span>¥{order.domestic_shipping?.toLocaleString()}</span>
                    </div>
                    <div className="order-price-row order-price-total">
                      <span>预估总计</span>
                      <span>¥{order.total_cny?.toLocaleString()}</span>
                    </div>
                  </div>

                  <div className="order-card-meta">
                    <span>📅 {order.created_at?.slice(0, 16)?.replace('T', ' ')}</span>
                    {order.note && <span>📝 {order.note}</span>}
                  </div>
                </div>

                {nextStatuses.length > 0 && (
                  <div className="order-card-actions">
                    <span className="order-action-label">更新状态：</span>
                    {nextStatuses.map((ns: string) => (
                      <button
                        key={ns}
                        className="btn btn-sm btn-outline"
                        onClick={() => handleStatusUpdate(order.id, ns)}
                      >
                        {STATUS_ICONS[ns]} {STATUS_LABELS[ns]}
                      </button>
                    ))}
                    <button
                      className="btn btn-sm btn-ghost"
                      onClick={() => handleDelete(order.id)}
                      style={{ marginLeft: 'auto' }}
                    >
                      删除
                    </button>
                  </div>
                )}

                {order.item_url && (
                  <div className="order-card-footer">
                    <a href={order.item_url} target="_blank" rel="noreferrer" className="btn btn-sm btn-ghost">
                      🔗 查看原始商品
                    </a>
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}