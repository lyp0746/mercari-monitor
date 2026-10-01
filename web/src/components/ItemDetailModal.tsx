import React, { useEffect, useState } from 'react'
import { itemDetail, orderApi, blocked } from '../api/client'

const PLATFORM_EMOJI: Record<string, string> = {
  mercari_jp: '🇯🇵', bunjang: '🇰🇷', paypay_fleamarket: '🇯🇵',
  fril: '🇯🇵', yahoo_auctions: '🇯🇵', carousell: '🌏',
  surugaya: '🇯🇵', rakuten: '🇯🇵', yahoo_shopping: '🇯🇵',
}

const PLATFORM_NAMES: Record<string, string> = {
  mercari_jp: 'Mercari', bunjang: 'Bunjang', paypay_fleamarket: 'PayPay',
  fril: 'Rakuma', yahoo_auctions: 'Yahoo拍卖', carousell: 'Carousell',
  surugaya: '駿河屋', rakuten: '楽天', yahoo_shopping: 'Yahoo购物',
}

const CURRENCY: Record<string, string> = {
  JPY: '¥', KRW: '₩', SGD: 'S$', HKD: 'HK$',
  TWD: 'NT$', MYR: 'RM', AUD: 'A$', PHP: '₱',
}

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

export default function ItemDetailModal({
  itemId,
  platform,
  onClose,
}: {
  itemId: string
  platform: string
  onClose: () => void
}) {
  const [detail, setDetail] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [ordering, setOrdering] = useState(false)
  const [orderSuccess, setOrderSuccess] = useState(false)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    itemDetail.get(itemId, platform).then(d => {
      if (!cancelled) {
        setDetail(d)
        setLoading(false)
      }
    }).catch(() => {
      if (!cancelled) setLoading(false)
    })
    return () => { cancelled = true }
  }, [itemId, platform])

  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', handleKey)
    return () => window.removeEventListener('keydown', handleKey)
  }, [onClose])

  const handleOrder = async () => {
    if (!detail || ordering) return
    setOrdering(true)
    try {
      await orderApi.create({
        item_id: detail.item_id,
        platform: detail.platform,
        item_name: detail.name,
        item_url: detail.url,
        image_url: detail.image_url,
        price: detail.price,
        currency: detail.currency,
        order_type: detail.is_auction ? 'bid' : 'buy',
      })
      setOrderSuccess(true)
      const d = await itemDetail.get(itemId, platform)
      setDetail(d)
    } catch (err: any) {
      alert(err.message || '下单失败')
    } finally {
      setOrdering(false)
    }
  }

  const handleBlock = async () => {
    if (!detail) return
    try {
      await blocked.add(detail.item_id, detail.platform)
      onClose()
    } catch (err) {
      console.error('屏蔽失败:', err)
    }
  }

  const emoji = PLATFORM_EMOJI[platform] || '📦'
  const platName = PLATFORM_NAMES[platform] || platform

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content" onClick={e => e.stopPropagation()}>
        <button className="modal-close" onClick={onClose}>✕</button>

        {loading ? (
          <div className="modal-loading">
            <span className="spinner" /> 加载中...
          </div>
        ) : !detail ? (
          <div className="modal-loading">商品信息获取失败</div>
        ) : (
          <>
            <div className="modal-header">
              <div className="modal-image-wrap">
                {detail.image_url ? (
                  <img src={detail.image_url} alt={detail.name} className="modal-image" />
                ) : (
                  <div className="modal-image-placeholder">{emoji}</div>
                )}
                <span className={`item-card-platform ${platform}`}>
                  {emoji} {platName}
                </span>
                {detail.is_auction && (
                  <span className="item-card-badge auction" style={{ position: 'absolute', top: 12, left: 12 }}>
                    拍卖
                  </span>
                )}
              </div>

              <div className="modal-info">
                <h2 className="modal-title">{detail.name}</h2>

                <div className="modal-price-section">
                  <div className="modal-price-main">
                    {CURRENCY[detail.currency] || ''}{detail.price?.toLocaleString()}
                  </div>
                  {detail.cny_price > 0 && (
                    <div className="modal-price-cny">≈ ¥{detail.cny_price.toLocaleString()} CNY</div>
                  )}
                </div>

                <div className="modal-meta-grid">
                  {detail.condition_label && (
                    <div className="modal-meta-item">
                      <span className="modal-meta-label">成色</span>
                      <span className="modal-meta-value">{detail.condition_label}</span>
                    </div>
                  )}
                  {detail.seller && (
                    <div className="modal-meta-item">
                      <span className="modal-meta-label">卖家</span>
                      <span className="modal-meta-value">{detail.seller}</span>
                    </div>
                  )}
                  {detail.keyword && (
                    <div className="modal-meta-item">
                      <span className="modal-meta-label">关键词</span>
                      <span className="modal-meta-value">{detail.keyword}</span>
                    </div>
                  )}
                  {detail.found_at && (
                    <div className="modal-meta-item">
                      <span className="modal-meta-label">发现时间</span>
                      <span className="modal-meta-value">{detail.found_at}</span>
                    </div>
                  )}
                </div>
              </div>
            </div>

            <div className="modal-cost-card">
              <h3 className="modal-cost-title">💰 费用明细</h3>
              <div className="modal-cost-rows">
                <div className="modal-cost-row">
                  <span>商品价格</span>
                  <span>¥{detail.cost_breakdown?.item_price_cny?.toLocaleString() ?? '-'}</span>
                </div>
                <div className="modal-cost-row">
                  <span>服务费 ({detail.cost_breakdown?.service_fee_rate ?? '8%'})</span>
                  <span>¥{detail.cost_breakdown?.service_fee?.toLocaleString() ?? '-'}</span>
                </div>
                <div className="modal-cost-row">
                  <span>{detail.cost_breakdown?.domestic_shipping_label ?? '日本国内运费'}</span>
                  <span>¥{detail.cost_breakdown?.domestic_shipping ?? '-'}</span>
                </div>
                <div className="modal-cost-row">
                  <span>{detail.cost_breakdown?.intl_shipping_label ?? '国际运费'}</span>
                  <span>到仓后计算</span>
                </div>
                <div className="modal-cost-row modal-cost-total">
                  <span>预估总计</span>
                  <span>¥{detail.cost_breakdown?.total_cny?.toLocaleString() ?? '-'}</span>
                </div>
              </div>
            </div>

            {detail.order && (
              <div className="modal-order-status">
                <span className="modal-order-badge" style={{ background: STATUS_COLORS[detail.order.status] || '#6b7280' }}>
                  {STATUS_LABELS[detail.order.status] || detail.order.status}
                </span>
                <span className="modal-order-label">订单状态</span>
              </div>
            )}

            <div className="modal-actions">
              {detail.url && (
                <a href={detail.url} target="_blank" rel="noreferrer" className="btn btn-outline">
                  🔗 原始链接
                </a>
              )}
              {!detail.order && !orderSuccess && (
                <button
                  className="btn btn-primary"
                  disabled={ordering}
                  onClick={handleOrder}
                >
                  {ordering ? '提交中...' : detail.is_auction ? '🔨 一键代拍' : '🛒 一键代购'}
                </button>
              )}
              {orderSuccess && (
                <span className="tag tag-success" style={{ padding: '8px 16px' }}>✅ 已下单</span>
              )}
              <button className="btn btn-ghost" onClick={handleBlock}>
                🚫 屏蔽
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}