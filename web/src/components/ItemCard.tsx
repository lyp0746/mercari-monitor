import React, { useState } from 'react'
import { timeAgo } from '../utils/timeUtils'
import { blocked } from '../api/client'
import ItemDetailModal from './ItemDetailModal'

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

const CONDITION_MAP: Record<string, string> = {
  new: '全新', like_new: '几乎全新', very_good: '非常好',
  good: '良好', acceptable: '可接受', poor: '较差',
}

const JPY_CNY_RATE = 0.048

export default function ItemCard({ item }: { item: any; onClick?: () => void }) {
  const [showDetail, setShowDetail] = useState(false)
  const emoji = PLATFORM_EMOJI[item.platform] || '📦'
  const platName = PLATFORM_NAMES[item.platform] || item.platform
  const sym = CURRENCY[item.currency] || item.currency || ''
  const condition = item.condition ? (CONDITION_MAP[item.condition] || item.condition) : ''
  const isAuction = !!item.is_auction
  const isWatchedSeller = !!item.watched_seller
  const oldPrice = item.old_price
  const imageUrl = item.image_url || ''
  const priceDrop = oldPrice && item.price && oldPrice > item.price
  const timeText = timeAgo(item.found_at)

  const cnyPrice = item.currency === 'JPY' && item.price
    ? Math.round(item.price * JPY_CNY_RATE)
    : null

  const handleBlock = async (e: React.MouseEvent) => {
    e.stopPropagation()
    try {
      await blocked.add(item.item_id, item.platform)
      const card = (e.currentTarget as HTMLElement).closest('.item-card')
      if (card) {
        card.classList.add('item-card-blocked')
      }
    } catch (err) {
      console.error('屏蔽失败:', err)
    }
  }

  const handleOpenUrl = (e: React.MouseEvent) => {
    e.stopPropagation()
    if (item.url) window.open(item.url, '_blank')
  }

  return (
    <>
      <div className="item-card" onClick={() => setShowDetail(true)}>
        <div className="item-card-image">
          {imageUrl ? (
            <img src={imageUrl} alt="" loading="lazy"
                 onError={(e) => { (e.target as HTMLElement).style.display = 'none' }} />
          ) : (
            <div className="item-card-placeholder">
              <span>{emoji}</span>
            </div>
          )}
          <span className={`item-card-platform ${item.platform || ''}`}>
            {emoji} {platName}
          </span>
          <div className="item-card-badges">
            {isAuction && <span className="item-card-badge auction">拍卖</span>}
            {isWatchedSeller && <span className="item-card-badge watched">关注</span>}
            {priceDrop && <span className="item-card-badge price-drop">降价</span>}
          </div>
        </div>

        <div className="item-card-body">
          <div className="item-card-name">{item.name}</div>
          <div className="item-card-price">
            <span className="item-card-price-main">{sym}{item.price?.toLocaleString()}</span>
            {cnyPrice && (
              <span className="item-card-price-cny">≈ ¥{cnyPrice.toLocaleString()}</span>
            )}
            {oldPrice && (
              <span className="item-card-price-old">{sym}{oldPrice.toLocaleString()}</span>
            )}
          </div>
          <div className="item-card-meta">
            {condition && <span className="item-card-condition">📊 {condition}</span>}
            {item.keyword && <span className="item-card-kw">🔍 {item.keyword}</span>}
            {timeText && <span className="item-card-time">{timeText}</span>}
          </div>
        </div>

        <div className="item-card-actions">
          {item.url && (
            <button className="btn btn-sm btn-primary" onClick={handleOpenUrl}>
              查看商品
            </button>
          )}
          <button className="btn btn-sm btn-ghost item-block-action" onClick={handleBlock}>
            🚫 屏蔽
          </button>
        </div>
      </div>

      {showDetail && (
        <ItemDetailModal
          itemId={item.item_id}
          platform={item.platform}
          onClose={() => setShowDetail(false)}
        />
      )}
    </>
  )
}