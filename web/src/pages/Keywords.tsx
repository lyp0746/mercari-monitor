import React, { useEffect, useState } from 'react'
import { keywords } from '../api/client'

const PLATFORMS = [
  { id: 'mercari_jp', name: '煤炉', flag: '🇯🇵' },
  { id: 'yahoo_auctions', name: 'Yahoo拍卖', flag: '🇯🇵' },
  { id: 'surugaya', name: '駿河屋', flag: '🇯🇵' },
  { id: 'rakuten', name: '楽天', flag: '🇯🇵' },
  { id: 'yahoo_shopping', name: 'Yahoo购物', flag: '🇯🇵' },
  { id: 'paypay_fleamarket', name: 'PayPay', flag: '🇯🇵' },
  { id: 'fril', name: 'Rakuma', flag: '🇯🇵' },
  { id: 'bunjang', name: '번장', flag: '🇰🇷' },
  { id: 'carousell', name: 'Carousell', flag: '🌏' },
]

const CONDITIONS = [
  { value: 'new', label: '全新' },
  { value: 'like_new', label: '几乎全新' },
  { value: 'very_good', label: '非常好' },
  { value: 'good', label: '良好' },
  { value: 'acceptable', label: '可接受' },
  { value: 'poor', label: '较差' },
]

// 煤炉一级分类（Turbo 分类 Feed 加速用，仅 mercari_jp 生效）
const MERCARI_CATEGORIES = [
  { id: '', name: '不限（默认全量Feed）' },
  { id: '2', name: '👗 レディース' },
  { id: '3', name: '👔 メンズ' },
  { id: '4', name: '👶 ベビー・キッズ' },
  { id: '5', name: '🏠 インテリア・住まい・小物' },
  { id: '6', name: '🧸 おもちゃ・ホビー・グッズ' },
  { id: '7', name: '💄 コスメ・美容・ヘアケア' },
  { id: '8', name: '📷 家電・スマホ・カメラ' },
  { id: '9', name: '⚽ スポーツ・レジャー' },
  { id: '10', name: '🎨 ハンドメイド' },
  { id: '11', name: '🎫 チケット' },
  { id: '12', name: '🚗 自動車・バイク' },
  { id: '13', name: '📦 その他' },
]

export default function Keywords() {
  const [list, setList] = useState<any[]>([])
  const [form, setForm] = useState({
    keyword: '',
    platforms: ['mercari_jp', 'bunjang', 'paypay_fleamarket', 'fril', 'yahoo_auctions', 'carousell'],
    min_price: 0,
    max_price: 0,
    poll_interval: 0,
    noshops: false,
    allowed_conditions: ['new', 'like_new', 'very_good', 'good', 'acceptable', 'poor'].join(','),
    price_drop: true,
    category_id: '',
  })
  const [loading, setLoading] = useState(false)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [filterPlatform, setFilterPlatform] = useState('')

  async function load() {
    const d = await keywords.list()
    setList(d.items || [])
  }

  useEffect(() => { load() }, [])

  async function handleAdd(e: React.FormEvent) {
    e.preventDefault()
    if (!form.keyword.trim()) return
    if (!editingId && (!form.platforms || form.platforms.length === 0)) {
      alert('请至少选择一个平台')
      return
    }
    setLoading(true)
    try {
      if (editingId) {
        await keywords.update(editingId, form)
        setEditingId(null)
      } else {
        const selectedPlatforms = form.platforms
        for (const platform of selectedPlatforms) {
          await keywords.add({
            ...form,
            platform,
            platforms: undefined
          })
        }
      }
      setForm({
        keyword: '',
        platforms: ['mercari_jp', 'bunjang', 'paypay_fleamarket', 'fril', 'yahoo_auctions', 'carousell'],
        min_price: 0, max_price: 0,
        poll_interval: 0, noshops: false,
        allowed_conditions: ['new', 'like_new', 'very_good', 'good', 'acceptable', 'poor'].join(','),
        price_drop: true,
        category_id: '',
      })
      setShowAdvanced(false)
      await load()
    } finally { setLoading(false) }
  }

  async function handleDelete(id: number) {
    await keywords.delete(id)
    await load()
  }

  async function handleToggle(id: number, enabled: boolean) {
    await keywords.toggle(id, enabled)
    await load()
  }

  function handleEdit(kw: any) {
    setEditingId(kw.id)
    const conditions = kw.allowed_conditions || ''
    const hasConditions = conditions && conditions.trim().length > 0
    setForm({
      keyword: kw.keyword,
      platforms: [kw.platform],
      min_price: kw.min_price || 0,
      max_price: kw.max_price || 0,
      poll_interval: kw.poll_interval || 0,
      noshops: !!kw.noshops,
      allowed_conditions: hasConditions ? conditions : ['new', 'like_new', 'very_good', 'good', 'acceptable', 'poor'].join(','),
      price_drop: kw.price_drop !== undefined ? !!kw.price_drop : true,
      category_id: kw.category_id || '',
    })
    setShowAdvanced(true)
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  function toggleCondition(value: string) {
    const current = form.allowed_conditions ? form.allowed_conditions.split(',').filter(Boolean) : []
    const idx = current.indexOf(value)
    if (idx >= 0) current.splice(idx, 1)
    else current.push(value)
    setForm({ ...form, allowed_conditions: current.join(',') })
  }

  function toggleAllConditions() {
    const allConditions = CONDITIONS.map(c => c.value).join(',')
    const current = form.allowed_conditions || ''
    if (current === allConditions) setForm({ ...form, allowed_conditions: '' })
    else setForm({ ...form, allowed_conditions: allConditions })
  }

  function togglePlatform(platformId: string) {
    const current = form.platforms || []
    const idx = current.indexOf(platformId)
    let newPlatforms
    if (idx >= 0) newPlatforms = current.filter(p => p !== platformId)
    else newPlatforms = [...current, platformId]
    setForm({ ...form, platforms: newPlatforms })
  }

  function toggleAllPlatforms() {
    const allPlatformIds = PLATFORMS.map(p => p.id)
    const current = form.platforms || []
    const isAllSelected = allPlatformIds.every(id => current.includes(id))
    if (isAllSelected) setForm({ ...form, platforms: [] })
    else setForm({ ...form, platforms: [...allPlatformIds] })
  }

  const filteredList = filterPlatform
    ? list.filter(kw => kw.platform === filterPlatform)
    : list

  const activeCount = list.filter(kw => kw.enabled).length

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1 className="page-title">📡 监控任务</h1>
          <p className="page-subtitle">管理关键词监控，自动发现日本好物</p>
        </div>
        <div className="kw-stats-row">
          <span className="tag tag-accent">{list.length} 个任务</span>
          <span className="tag tag-success">{activeCount} 运行中</span>
        </div>
      </div>

      <div className="kw-add-card">
        <div className="kw-add-title">
          {editingId ? '✏️ 编辑关键词' : '➕ 添加监控关键词'}
        </div>
        <form onSubmit={handleAdd} className="kw-form">
          <div className="kw-form-row">
            <input
              type="text"
              placeholder="输入搜索关键词，如：ガチャ 限定、ねんどろいど..."
              value={form.keyword}
              onChange={e => setForm({ ...form, keyword: e.target.value })}
              className="input kw-keyword-input"
            />
            <button type="submit" disabled={loading || !form.keyword.trim()}
                    className="btn btn-primary">
              {loading ? '...' : editingId ? '保存修改' : '添加'}
            </button>
            {editingId && (
              <button type="button" onClick={() => {
                setEditingId(null)
                setForm({
                  keyword: '',
                  platforms: ['mercari_jp', 'bunjang', 'paypay_fleamarket', 'fril', 'yahoo_auctions', 'carousell'],
                  min_price: 0, max_price: 0,
                  poll_interval: 0, noshops: false,
                  allowed_conditions: ['new', 'like_new', 'very_good', 'good', 'acceptable', 'poor'].join(','),
                  price_drop: true,
                  category_id: '',
                })
                setShowAdvanced(false)
              }} className="btn btn-ghost btn-sm">取消</button>
            )}
          </div>

          <div className="kw-platform-row">
            <button type="button"
                    className={`btn btn-sm ${form.platforms?.length === PLATFORMS.length ? 'btn-primary' : 'btn-outline'}`}
                    onClick={toggleAllPlatforms}>
              全部平台
            </button>
            <div className="kw-platform-chips">
              {PLATFORMS.map(p => {
                const isSelected = form.platforms?.includes(p.id)
                return (
                  <button key={p.id} type="button"
                          className={`kw-p-chip ${isSelected ? 'selected' : ''}`}
                          onClick={() => togglePlatform(p.id)}>
                    {p.flag} {p.name}
                  </button>
                )
              })}
            </div>
          </div>

          <div className="kw-price-row">
            <input type="number" placeholder="最低价 ¥"
                   value={form.min_price || ''} min={0}
                   onChange={e => setForm({ ...form, min_price: Number(e.target.value) })}
                   className="input kw-price-input" />
            <span className="kw-price-sep">~</span>
            <input type="number" placeholder="最高价 ¥"
                   value={form.max_price || ''} min={0}
                   onChange={e => setForm({ ...form, max_price: Number(e.target.value) })}
                   className="input kw-price-input" />
            <button type="button" onClick={() => setShowAdvanced(!showAdvanced)}
                    className="btn btn-outline btn-sm">
              {showAdvanced ? '收起高级' : '⚙️ 高级'}
            </button>
          </div>
        </form>

        {showAdvanced && (
          <div className="kw-advanced-card">
            <div className="adv-field">
              <label>自定义轮询率（秒）</label>
              <input type="number" value={form.poll_interval || ''}
                     onChange={e => setForm({ ...form, poll_interval: Number(e.target.value) })}
                     min={2} max={60} step={0.5}
                     placeholder="留空使用全局设置" className="input" />
              <span className="adv-hint">范围 2-60s，留空使用全局轮询率</span>
            </div>
            <div className="adv-field">
              <label className="checkbox-label">
                <input type="checkbox" checked={form.noshops}
                       onChange={e => setForm({ ...form, noshops: e.target.checked })} />
                过滤商城商品（#noshops）
              </label>
            </div>
            <div className="adv-field">
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <label>商品成色筛选</label>
                <button type="button"
                        className={`btn btn-sm ${form.allowed_conditions === CONDITIONS.map(c => c.value).join(',') ? 'btn-primary' : 'btn-outline'}`}
                        onClick={toggleAllConditions}>
                  {form.allowed_conditions === CONDITIONS.map(c => c.value).join(',') ? '取消全选' : '全选'}
                </button>
              </div>
              <div className="cond-chips">
                {CONDITIONS.map(c => {
                  const selected = form.allowed_conditions.split(',').filter(Boolean).includes(c.value)
                  return (
                    <button key={c.value} type="button"
                            className={`kw-p-chip ${selected ? 'selected' : ''}`}
                            onClick={() => toggleCondition(c.value)}>
                      {c.label}
                    </button>
                  )
                })}
              </div>
              <span className="adv-hint">默认全选，可取消不需要的成色</span>
            </div>
            <div className="adv-field">
              <label className="checkbox-label">
                <input type="checkbox" checked={form.price_drop}
                       onChange={e => setForm({ ...form, price_drop: e.target.checked })} />
                📉 启用降价提醒
              </label>
            </div>
            {form.platforms?.includes('mercari_jp') && (
              <div className="adv-field">
                <label>🚀 煤炉分类加速（可选）</label>
                <select className="input" value={form.category_id || ''}
                        onChange={e => setForm({ ...form, category_id: e.target.value })}>
                  {MERCARI_CATEGORIES.map(c => (
                    <option key={c.id || 'none'} value={c.id}>{c.name}</option>
                  ))}
                </select>
                <span className="adv-hint">
                  设置后 Turbo 会额外拉取该分类的新品流，对热门分类可提前到 5~15s 命中。
                  高级用户可填写子分类 ID（如 6→331）
                </span>
              </div>
            )}
          </div>
        )}
      </div>

      <div className="kw-filter-bar">
        <div className="platform-tabs">
          <button
            className={`platform-tab ${filterPlatform === '' ? 'active' : ''}`}
            onClick={() => setFilterPlatform('')}
          >
            <span className="tab-flag">📋</span>
            全部
          </button>
          {PLATFORMS.map(p => (
            <button
              key={p.id}
              className={`platform-tab ${filterPlatform === p.id ? 'active' : ''}`}
              onClick={() => setFilterPlatform(filterPlatform === p.id ? '' : p.id)}
            >
              <span className="tab-flag">{p.flag}</span>
              {p.name}
            </button>
          ))}
        </div>
      </div>

      <div className="kw-list">
        {filteredList.map(kw => (
          <div key={kw.id} className={`kw-card ${!kw.enabled ? 'disabled' : ''}`}>
            <div className="kw-card-main">
              <div className="kw-card-left">
                <span className="kw-name">{kw.keyword}</span>
                <div className="kw-card-tags">
                  <span className="tag tag-accent">{PLATFORMS.find(p => p.id === kw.platform)?.flag} {kw.platform_name || kw.platform}</span>
                  {kw.poll_interval > 0 && <span className="tag">⏱ {kw.poll_interval}s</span>}
                  {kw.noshops && <span className="tag tag-warning">🚫商城</span>}
                  {kw.price_drop && <span className="tag tag-success">📉降价</span>}
                  {kw.category_id && <span className="tag tag-accent">🚀分类{kw.category_id}</span>}
                </div>
              </div>
              <div className="kw-card-right">
                {(kw.min_price > 0 || kw.max_price > 0) && (
                  <span className="kw-range">
                    ¥{kw.min_price || 0} ~ ¥{kw.max_price || '∞'}
                  </span>
                )}
                <button onClick={() => handleEdit(kw)} className="btn btn-ghost btn-sm">编辑</button>
                <label className="toggle">
                  <input type="checkbox" checked={!!kw.enabled}
                         onChange={e => handleToggle(kw.id, e.target.checked)} />
                  <span className="toggle-slider" />
                </label>
                <button onClick={() => handleDelete(kw.id)} className="btn btn-ghost btn-sm kw-del-btn">删除</button>
              </div>
            </div>
          </div>
        ))}
        {filteredList.length === 0 && (
          <div className="empty">
            <div className="empty-icon">📡</div>
            <div className="empty-title">暂无监控任务</div>
            <div style={{ color: 'var(--text-muted)', fontSize: 13 }}>添加关键词后开始监控</div>
          </div>
        )}
      </div>
    </div>
  )
}