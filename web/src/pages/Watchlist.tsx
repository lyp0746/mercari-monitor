import React, { useEffect, useState } from 'react'
import { watchlist } from '../api/client'

const PLATFORMS = [
  { id: 'mercari_jp', name: '煤炉', flag: '🇯🇵' },
  { id: 'yahoo_auctions', name: 'Yahoo拍卖', flag: '🇯🇵' },
  { id: 'surugaya', name: '駿河屋', flag: '🇯🇵' },
  { id: 'rakuten', name: '楽天', flag: '🇯🇵' },
  { id: 'yahoo_shopping', name: 'Yahoo购物', flag: '🇯🇵' },
  { id: 'paypay_fleamarket', name: 'PayPay', flag: '🇯🇵' },
  { id: 'fril', name: 'Rakuma', flag: '🇯🇵' },
  { id: 'bunjang', name: 'Bunjang', flag: '🇰🇷' },
  { id: 'carousell', name: 'Carousell', flag: '🌏' },
]

export default function Watchlist() {
  const [tab, setTab] = useState<'sellers' | 'items'>('items')
  const [sellers, setSellers] = useState<any[]>([])
  const [items, setItems] = useState<any[]>([])
  const [form, setForm] = useState({ seller_id: '', platform: 'mercari_jp', alias: '' })
  const [itemForm, setItemForm] = useState({ item_id: '', platform: 'mercari_jp', name: '', url: '' })
  const [msg, setMsg] = useState<{ text: string; type: 'success' | 'error' } | null>(null)
  const [isAddingItem, setIsAddingItem] = useState(false)

  async function load() {
    try {
      const [s, i] = await Promise.all([watchlist.listSellers(), watchlist.listItems()])
      setSellers(s.items || [])
      setItems(i.items || [])
    } catch (err) {
      showMsg('加载失败，请刷新重试', 'error')
    }
  }

  useEffect(() => { load() }, [])

  function showMsg(text: string, type: 'success' | 'error') {
    setMsg({ text, type })
    setTimeout(() => setMsg(null), 3000)
  }

  async function addSeller(e: React.FormEvent) {
    e.preventDefault()
    if (!form.seller_id.trim()) {
      showMsg('请输入卖家ID', 'error')
      return
    }
    try {
      await watchlist.addSeller(form)
      setForm({ seller_id: '', platform: 'mercari_jp', alias: '' })
      showMsg('✓ 卖家添加成功', 'success')
      await load()
    } catch (err: any) {
      showMsg(err.message || '添加失败', 'error')
    }
  }

  async function addItem(e: React.FormEvent) {
    e.preventDefault()
    if (!itemForm.item_id.trim()) {
      showMsg('请输入商品ID', 'error')
      return
    }
    if (isAddingItem) return
    setIsAddingItem(true)
    try {
      const requestData = {
        item_id: itemForm.item_id.trim(),
        platform: itemForm.platform,
        name: itemForm.name.trim() || `商品-${itemForm.item_id.trim()}`,
        url: itemForm.url.trim()
      }
      await watchlist.addItem(requestData)
      setItemForm({ item_id: '', platform: 'mercari_jp', name: '', url: '' })
      showMsg('✓ 商品添加成功！系统将自动监控该商品的留言更新', 'success')
      await load()
    } catch (err: any) {
      let errorMsg = '添加失败，请重试'
      if (err?.message) {
        if (err.message.includes('401') || err.message.includes('未登录')) {
          errorMsg = '请先登录后再添加关注商品'
        } else if (err.message.includes('400') || err.message.includes('已存在')) {
          errorMsg = '该商品已在关注列表中'
        } else if (err.message.includes('500')) {
          errorMsg = '服务器错误，请稍后重试'
        } else {
          errorMsg = err.message
        }
      }
      showMsg(`❌ ${errorMsg}`, 'error')
    } finally {
      setIsAddingItem(false)
    }
  }

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1 className="page-title">⭐ 我的收藏</h1>
          <p className="page-subtitle">关注卖家和商品，实时追踪动态</p>
        </div>
      </div>

      {msg && (
        <div className={`toast ${msg.type === 'success' ? 'success' : 'error'}`}>
          {msg.text}
        </div>
      )}

      <div className="wl-tabs">
        <button className={`wl-tab ${tab === 'items' ? 'active' : ''}`}
                onClick={() => setTab('items')}>
          📦 关注商品 ({items.length})
        </button>
        <button className={`wl-tab ${tab === 'sellers' ? 'active' : ''}`}
                onClick={() => setTab('sellers')}>
          👤 关注卖家 ({sellers.length})
        </button>
      </div>

      {tab === 'items' && (
        <div className="wl-section">
          <div className="wl-hint-card">
            💡 添加关注商品后，系统会自动监控该商品的留言和议价更新，有新消息时推送通知
          </div>
          <div className="card wl-form-card">
            <div className="wl-form-title">➕ 添加关注商品</div>
            <form onSubmit={addItem} className="wl-form-items">
              <div className="wl-field">
                <label>商品ID</label>
                <input type="text" placeholder="例如：m53469270366" value={itemForm.item_id}
                       onChange={e => setItemForm({ ...itemForm, item_id: e.target.value })}
                       className="input" />
              </div>
              <div className="wl-field">
                <label>平台</label>
                <select value={itemForm.platform}
                        onChange={e => setItemForm({ ...itemForm, platform: e.target.value })}
                        className="select">
                  {PLATFORMS.map(p => <option key={p.id} value={p.id}>{p.flag} {p.name}</option>)}
                </select>
              </div>
              <div className="wl-field">
                <label>名称（可选）</label>
                <input type="text" placeholder="方便识别" value={itemForm.name}
                       onChange={e => setItemForm({ ...itemForm, name: e.target.value })}
                       className="input" />
              </div>
              <div className="wl-field wl-field-full">
                <label>URL（可选）</label>
                <input type="text" placeholder="https://jp.mercari.com/item/..." value={itemForm.url}
                       onChange={e => setItemForm({ ...itemForm, url: e.target.value })}
                       className="input" />
              </div>
              <div className="wl-actions">
                <button type="submit" className="btn btn-primary" disabled={isAddingItem}>
                  {isAddingItem ? '⏳ 添加中...' : '✓ 添加商品'}
                </button>
              </div>
            </form>
          </div>

          <div className="wl-list">
            {items.map((it, i) => (
              <div key={i} className="card wl-item-card">
                <div className="wl-item-info">
                  <div className="wl-item-name">{it.name || it.item_id}</div>
                  <div className="wl-item-meta">
                    <span className="tag tag-accent">{it.platform}</span>
                    {it.url && (
                      <a href={it.url} target="_blank" rel="noreferrer" className="wl-item-link">
                        查看商品 →
                      </a>
                    )}
                  </div>
                </div>
                <button onClick={() => watchlist.removeItem(it.item_id, it.platform).then(load)}
                        className="btn btn-ghost btn-sm">删除</button>
              </div>
            ))}
            {items.length === 0 && (
              <div className="empty">
                <div className="empty-icon">📦</div>
                <div className="empty-title">暂无关注商品</div>
                <div style={{ color: 'var(--text-muted)', fontSize: 13 }}>添加商品后自动监控动态</div>
              </div>
            )}
          </div>
        </div>
      )}

      {tab === 'sellers' && (
        <div className="wl-section">
          <div className="card wl-form-card">
            <div className="wl-form-title">➕ 添加关注卖家</div>
            <form onSubmit={addSeller} className="wl-form-row">
              <input type="text" placeholder="卖家 ID" value={form.seller_id}
                     onChange={e => setForm({ ...form, seller_id: e.target.value })}
                     className="input" />
              <select value={form.platform}
                      onChange={e => setForm({ ...form, platform: e.target.value })}
                      className="select">
                {PLATFORMS.map(p => <option key={p.id} value={p.id}>{p.flag} {p.name}</option>)}
              </select>
              <input type="text" placeholder="备注（可选）" value={form.alias}
                     onChange={e => setForm({ ...form, alias: e.target.value })}
                     className="input" />
              <button type="submit" className="btn btn-primary">添加</button>
            </form>
          </div>

          <div className="wl-list">
            {sellers.map((s, i) => (
              <div key={i} className="card wl-item-card">
                <div className="wl-item-info">
                  <div className="wl-item-name">{s.alias || s.seller_id}</div>
                  <div className="wl-item-meta">
                    <span className="tag tag-accent">{s.platform}</span>
                    {s.alias && <span className="tag">{s.seller_id}</span>}
                  </div>
                </div>
                <button onClick={() => watchlist.removeSeller(s.seller_id, s.platform).then(load)}
                        className="btn btn-ghost btn-sm">删除</button>
              </div>
            ))}
            {sellers.length === 0 && (
              <div className="empty">
                <div className="empty-icon">👤</div>
                <div className="empty-title">暂无关注卖家</div>
                <div style={{ color: 'var(--text-muted)', fontSize: 13 }}>关注卖家后追踪其上新动态</div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}