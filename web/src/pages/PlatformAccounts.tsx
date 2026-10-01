import React, { useEffect, useState } from 'react'
import { accounts } from '../api/client'

const PLATFORMS = [
  { id: 'mercari_jp', name: 'Mercari', emoji: '🇯🇵', desc: '日本煤炉' },
  { id: 'yahoo_auctions', name: 'Yahoo拍卖', emoji: '🇯🇵', desc: '雅虎拍卖' },
  { id: 'surugaya', name: '駿河屋', emoji: '🇯🇵', desc: '动漫/中古' },
  { id: 'rakuten', name: '楽天市場', emoji: '🇯🇵', desc: '乐天市场' },
  { id: 'yahoo_shopping', name: 'Yahoo购物', emoji: '🇯🇵', desc: '雅虎购物' },
  { id: 'paypay_fleamarket', name: 'PayPay', emoji: '🇯🇵', desc: 'PayPay闲置' },
  { id: 'fril', name: 'Rakuma', emoji: '🇯🇵', desc: 'Fril/Rakuma' },
  { id: 'bunjang', name: 'Bunjang', emoji: '🇰🇷', desc: '韩国番酱' },
  { id: 'carousell', name: 'Carousell', emoji: '🌏', desc: '旋转拍卖' },
]

export default function PlatformAccounts() {
  const [accountList, setAccountList] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [showAdd, setShowAdd] = useState(false)
  const [form, setForm] = useState({
    platform: 'mercari_jp',
    account_name: '',
    cookie: '',
    token: '',
    extra: '',
  })

  const fetchAccounts = async () => {
    setLoading(true)
    try {
      const res = await accounts.list()
      setAccountList(res.items || [])
    } catch (err) {
      console.error('获取账号列表失败:', err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchAccounts()
  }, [])

  const handleAdd = async () => {
    if (!form.account_name.trim()) {
      alert('请输入账号名称')
      return
    }
    try {
      await accounts.add(form)
      setShowAdd(false)
      setForm({ platform: 'mercari_jp', account_name: '', cookie: '', token: '', extra: '' })
      fetchAccounts()
    } catch (err) {
      console.error('添加账号失败:', err)
      alert('添加失败')
    }
  }

  const handleRemove = async (id: number) => {
    if (!confirm('确定删除此账号？')) return
    try {
      await accounts.remove(id)
      fetchAccounts()
    } catch (err) {
      console.error('删除失败:', err)
    }
  }

  const grouped = PLATFORMS.map(p => ({
    ...p,
    accounts: accountList.filter(a => a.platform === p.id),
  }))

  return (
    <div className="page-container">
      <div className="page-header">
        <div>
          <h1 className="page-title">🌐 平台账号</h1>
          <p className="page-subtitle">管理各平台登录凭证，用于自动下单和数据获取</p>
        </div>
        <button className="btn btn-primary" onClick={() => setShowAdd(true)}>
          ＋ 添加账号
        </button>
      </div>

      {showAdd && (
        <div className="modal-overlay" onClick={() => setShowAdd(false)}>
          <div className="modal-content modal-sm" onClick={e => e.stopPropagation()}>
            <button className="modal-close" onClick={() => setShowAdd(false)}>✕</button>
            <h2 className="modal-title" style={{ marginBottom: 16 }}>添加平台账号</h2>

            <div className="form-group">
              <label className="form-label">平台</label>
              <select
                className="form-select"
                value={form.platform}
                onChange={e => setForm(f => ({ ...f, platform: e.target.value }))}
              >
                {PLATFORMS.map(p => (
                  <option key={p.id} value={p.id}>{p.emoji} {p.name}</option>
                ))}
              </select>
            </div>

            <div className="form-group">
              <label className="form-label">账号名称</label>
              <input
                className="form-input"
                placeholder="如：my_mercari_account"
                value={form.account_name}
                onChange={e => setForm(f => ({ ...f, account_name: e.target.value }))}
              />
            </div>

            <div className="form-group">
              <label className="form-label">Cookie</label>
              <textarea
                className="form-textarea"
                rows={3}
                placeholder="从浏览器开发者工具复制Cookie"
                value={form.cookie}
                onChange={e => setForm(f => ({ ...f, cookie: e.target.value }))}
              />
            </div>

            <div className="form-group">
              <label className="form-label">Token（可选）</label>
              <input
                className="form-input"
                placeholder="API Token 或 Bearer Token"
                value={form.token}
                onChange={e => setForm(f => ({ ...f, token: e.target.value }))}
              />
            </div>

            <div className="form-group">
              <label className="form-label">备注（可选）</label>
              <input
                className="form-input"
                placeholder="额外信息"
                value={form.extra}
                onChange={e => setForm(f => ({ ...f, extra: e.target.value }))}
              />
            </div>

            <div className="modal-actions">
              <button className="btn btn-ghost" onClick={() => setShowAdd(false)}>取消</button>
              <button className="btn btn-primary" onClick={handleAdd}>添加</button>
            </div>
          </div>
        </div>
      )}

      {loading ? (
        <div className="loading-state"><span className="spinner" /> 加载中...</div>
      ) : (
        <div className="platform-accounts-grid">
          {grouped.map(group => (
            <div key={group.id} className="platform-account-card">
              <div className="platform-account-header">
                <span className="platform-account-emoji">{group.emoji}</span>
                <div>
                  <div className="platform-account-name">{group.name}</div>
                  <div className="platform-account-desc">{group.desc}</div>
                </div>
                <span className="platform-account-count">
                  {group.accounts.length} 个账号
                </span>
              </div>

              {group.accounts.length === 0 ? (
                <div className="platform-account-empty">
                  暂未配置账号
                </div>
              ) : (
                <div className="platform-account-list">
                  {group.accounts.map(acc => (
                    <div key={acc.id} className="platform-account-item">
                      <div className="platform-account-item-info">
                        <span className="platform-account-item-name">{acc.account_name}</span>
                        <span className="platform-account-item-date">
                          添加于 {acc.created_at?.slice(0, 10)}
                        </span>
                      </div>
                      <button
                        className="btn btn-sm btn-ghost"
                        onClick={() => handleRemove(acc.id)}
                      >
                        删除
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}