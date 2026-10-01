import React, { useEffect, useState } from 'react'
import { settings, monitor } from '../api/client'

const CURRENCIES = [
  { code: 'jpy', label: 'JPY 日元', flag: '🇯🇵' },
  { code: 'krw', label: 'KRW 韩元', flag: '🇰🇷' },
  { code: 'sgd', label: 'SGD 新加坡元', flag: '🇸🇬' },
  { code: 'hkd', label: 'HKD 港币', flag: '🇭🇰' },
  { code: 'twd', label: 'TWD 台币', flag: '🇹🇼' },
  { code: 'myr', label: 'MYR 马来西亚令吉', flag: '🇲🇾' },
  { code: 'aud', label: 'AUD 澳元', flag: '🇦🇺' },
  { code: 'php', label: 'PHP 菲律宾比索', flag: '🇵🇭' },
]

const SETTINGS_TABS = [
  { id: 'notify', icon: '🔔', label: '消息推送' },
  { id: 'rates', icon: '💱', label: '汇率设置' },
  { id: 'proxy', icon: '🌐', label: '代理设置' },
  { id: 'poll', icon: '⏱️', label: '轮询间隔' },
  { id: 'filter', icon: '🚫', label: '过滤规则' },
  { id: 'monitor', icon: '⚡', label: '监控控制' },
]

export default function Settings() {
  const [activeTab, setActiveTab] = useState('notify')
  const [cfg, setCfg] = useState({
    telegram_token: '',
    telegram_chat_id: '',
    telegram_enabled: true,
    telegram_bot_enabled: false,
    discord_webhook: '',
    discord_enabled: true,
    carousell_regions: 'SG',
    proxies: '',
    proxy_platforms: 'mercari_jp',
    poll_interval: '1.0',
    seller_blacklist: '',
    auction_notify_mode: 'new',
    auction_ending_threshold: '3600',
    per_platform_interval: {} as Record<string, string>,
  })
  const [rates, setRates] = useState<Record<string, string>>({})
  const [msg, setMsg] = useState('')

  useEffect(() => {
    settings.get().then((d: any) => {
      setCfg({
        telegram_token: d.telegram_token || '',
        telegram_chat_id: d.telegram_chat_id || '',
        telegram_enabled: d.telegram_enabled !== false,
        telegram_bot_enabled: d.telegram_bot_enabled === true,
        discord_webhook: d.discord_webhook_url || d.discord_webhook || '',
        discord_enabled: d.discord_enabled !== false,
        carousell_regions: d.carousell_regions || 'SG',
        proxies: d.proxies || '',
        proxy_platforms: d.proxy_platforms || 'mercari_jp',
        poll_interval: d.poll_interval || '1.0',
        seller_blacklist: d.seller_blacklist || '',
        auction_notify_mode: d.auction_notify_mode || 'new',
        auction_ending_threshold: d.auction_ending_threshold || '3600',
        per_platform_interval: d.per_platform_interval || {},
      })
      setRates(d.exchange_rates || {})
    })
  }, [])

  async function save() {
    await settings.update({ ...cfg, exchange_rates: rates })
    showMsg('✓ 已保存')
  }

  async function testTg() {
    setMsg('保存并发送中...')
    await settings.update({ telegram_token: cfg.telegram_token, telegram_chat_id: cfg.telegram_chat_id, telegram_enabled: cfg.telegram_enabled })
    const r: any = await settings.testTelegram()
    showMsg(r.message, r.ok ? 'ok' : 'err')
  }

  async function testDiscord() {
    setMsg('测试Discord...')
    try {
      const resp = await fetch('/api/settings/test-discord', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ webhook_url: cfg.discord_webhook })
      })
      const r = await resp.json()
      showMsg(r.message || (r.ok ? 'Discord发送成功' : 'Discord发送失败'), r.ok ? 'ok' : 'err')
    } catch (e: any) {
      showMsg('连接失败: ' + e.message, 'err')
    }
  }

  function showMsg(text: string, type?: string) {
    setMsg(text)
    setTimeout(() => setMsg(''), 4000)
  }

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1 className="page-title">⚙️ 我的设置</h1>
          <p className="page-subtitle">管理推送通知、汇率、代理等配置</p>
        </div>
      </div>

      <div className="settings-layout">
        <div className="settings-sidebar">
          {SETTINGS_TABS.map(tab => (
            <button
              key={tab.id}
              className={`settings-nav-item ${activeTab === tab.id ? 'active' : ''}`}
              onClick={() => setActiveTab(tab.id)}
            >
              <span>{tab.icon}</span>
              <span>{tab.label}</span>
            </button>
          ))}
        </div>

        <div className="settings-content">
          {activeTab === 'notify' && (
            <>
              <div className="card">
                <h3 className="set-section-title">✈️ Telegram 推送</h3>
                <div className="set-field">
                  <label className="checkbox-label">
                    <input type="checkbox" checked={cfg.telegram_enabled}
                           onChange={e => setCfg(c => ({ ...c, telegram_enabled: e.target.checked }))} />
                    启用 Telegram 推送
                  </label>
                </div>
                <div className="set-field">
                  <label className="checkbox-label">
                    <input type="checkbox" checked={cfg.telegram_bot_enabled}
                           onChange={e => setCfg(c => ({ ...c, telegram_bot_enabled: e.target.checked }))} />
                    启用 Bot 命令服务 (/start, /stats 等)
                  </label>
                </div>
                <div className="set-field">
                  <label>Token</label>
                  <input type="password" value={cfg.telegram_token}
                         onChange={e => setCfg(c => ({ ...c, telegram_token: e.target.value }))}
                         placeholder="从 @BotFather 获取" className="input" />
                </div>
                <div className="set-field">
                  <label>Chat ID</label>
                  <input type="text" value={cfg.telegram_chat_id}
                         onChange={e => setCfg(c => ({ ...c, telegram_chat_id: e.target.value }))}
                         placeholder="用户或群组 ID" className="input" />
                </div>
                <div className="set-actions">
                  <button onClick={testTg} className="btn btn-outline">测试发送</button>
                  <button onClick={save} className="btn btn-primary">保存设置</button>
                </div>
              </div>

              <div className="card" style={{ marginTop: 20 }}>
                <h3 className="set-section-title">🎮 Discord 推送</h3>
                <div className="set-field">
                  <label className="checkbox-label">
                    <input type="checkbox" checked={cfg.discord_enabled}
                           onChange={e => setCfg(c => ({ ...c, discord_enabled: e.target.checked }))} />
                    启用 Discord 推送
                  </label>
                </div>
                <div className="set-field">
                  <label>Webhook URL</label>
                  <input type="text" value={cfg.discord_webhook}
                         onChange={e => setCfg(c => ({ ...c, discord_webhook: e.target.value }))}
                         placeholder="https://discord.com/api/webhooks/..." className="input" />
                  <span className="set-hint">从 Discord 频道 → 整合 → Webhooks 获取</span>
                </div>
                <div className="set-actions">
                  <button onClick={testDiscord} className="btn btn-outline">测试发送</button>
                  <button onClick={save} className="btn btn-primary">保存设置</button>
                </div>
              </div>

              <div className="card" style={{ marginTop: 20 }}>
                <h3 className="set-section-title">🚨 拍卖通知模式</h3>
                <div className="set-field">
                  <label>通知时机</label>
                  <div className="radio-group">
                    <label className="radio-item">
                      <input type="radio" name="auction_mode"
                             checked={cfg.auction_notify_mode === 'new'}
                             onChange={() => setCfg(c => ({ ...c, auction_notify_mode: 'new' }))} />
                      <span>上新即通知（默认）</span>
                    </label>
                    <label className="radio-item">
                      <input type="radio" name="auction_mode"
                             checked={cfg.auction_notify_mode === 'ending'}
                             onChange={() => setCfg(c => ({ ...c, auction_notify_mode: 'ending' }))} />
                      <span>临近结束时通知</span>
                    </label>
                  </div>
                </div>
                {cfg.auction_notify_mode === 'ending' && (
                  <div className="set-field">
                    <label>提前通知时间（秒）</label>
                    <input type="number" value={cfg.auction_ending_threshold}
                           onChange={e => setCfg(c => ({ ...c, auction_ending_threshold: e.target.value }))}
                           min={60} step={60} className="input" style={{ width: 140 }} />
                    <span className="set-hint">默认 3600 秒（1小时）</span>
                  </div>
                )}
                <p className="set-hint">选择「临近结束」模式后，拍卖商品上新时仅记录，剩余时间不足阈值时才推送通知。</p>
                <button onClick={save} className="btn btn-primary">保存设置</button>
              </div>
            </>
          )}

          {activeTab === 'rates' && (
            <div className="card">
              <h3 className="set-section-title">💱 汇率设置（→ CNY 人民币）</h3>
              <div className="rates-grid">
                {CURRENCIES.map(cur => (
                  <div key={cur.code} className="rate-row">
                    <span className="rate-label">{cur.flag} {cur.code.toUpperCase()}</span>
                    <input type="number" step="0.0001"
                           value={rates[cur.code] || ''}
                           onChange={e => setRates(r => ({ ...r, [cur.code]: e.target.value }))}
                           placeholder="0" className="input" style={{ width: 120 }} />
                    <span className="rate-arrow">→ ¥</span>
                  </div>
                ))}
              </div>
              <p className="set-hint">1 单位外币 = ? 人民币。推送时自动换算显示。</p>
              <button onClick={save} className="btn btn-primary">保存汇率</button>
            </div>
          )}

          {activeTab === 'proxy' && (
            <div className="card">
              <h3 className="set-section-title">🌐 代理 IP</h3>
              <div className="set-field">
                <label>代理地址（每行一个）</label>
                <textarea rows={6} value={cfg.proxies}
                          onChange={e => setCfg(c => ({ ...c, proxies: e.target.value }))}
                          placeholder={"http://ip:port\nsocks5://user:pass@ip:port\nhttps://ip:port"}
                          className="textarea" />
              </div>
              <p className="set-hint">轮换使用降低被封风险。支持 HTTP / HTTPS / SOCKS5。</p>
              <div className="set-field">
                <label>使用代理的平台（逗号分隔）</label>
                <input type="text" value={cfg.proxy_platforms}
                       onChange={e => setCfg(c => ({ ...c, proxy_platforms: e.target.value }))}
                       placeholder="mercari_jp" className="input" />
                <span className="set-hint">留空默认仅 Mercari 使用代理。可选: mercari_jp, yahoo_auctions, paypay_fleamarket, fril, bunjang, carousell</span>
              </div>
              <button onClick={save} className="btn btn-primary">保存代理</button>
            </div>
          )}

          {activeTab === 'poll' && (
            <>
              <div className="card">
                <h3 className="set-section-title">⏱️ 全局轮询间隔</h3>
                <div className="set-field">
                  <label>搜索间隔（秒）</label>
                  <input type="number" value={cfg.poll_interval}
                         onChange={e => setCfg(c => ({ ...c, poll_interval: e.target.value }))}
                         placeholder="1.0" min={0.5} max={60} step={0.1}
                         className="input" style={{ width: 140 }} />
                  <span className="set-hint">默认 1.0s，范围 0.5-60s</span>
                </div>
                <p className="set-hint">全局默认值，可在关键词中单独设置每个关键词的轮询率。</p>
                <button onClick={save} className="btn btn-primary">保存设置</button>
              </div>

              <div className="card" style={{ marginTop: 20 }}>
                <h3 className="set-section-title">📡 各平台轮询间隔</h3>
                <p className="set-hint" style={{ marginBottom: 16 }}>每个平台独立轮询，以下为推荐值。留空则使用平台默认值。</p>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                  {[
                    { id: 'mercari_jp', label: 'Mercari JP', def: '1.0', min: 0.3, hint: 'Turbo全量Feed 0.3s极速，API模式1s轮询', ok: true },
                    { id: 'yahoo_auctions', label: 'Yahoo Auctions', def: '2.0', min: 0.5, hint: 'Yahoo 反爬严格，2s 间隔防止触发验证码', ok: true },
                    { id: 'surugaya', label: '駿河屋 Surugaya', def: '2.0', min: 1.0, hint: '动漫/中古核心渠道，2s间隔稳定可靠', ok: true },
                    { id: 'rakuten', label: '楽天市場 Rakuten', def: '3.0', min: 1.0, hint: '乐天反爬中等，3s间隔安全', ok: true },
                    { id: 'yahoo_shopping', label: 'Yahoo!ショッピング', def: '3.0', min: 1.0, hint: '雅虎购物与拍卖同源，3s间隔', ok: true },
                    { id: 'paypay_fleamarket', label: 'PayPay Flea', def: '5.0', min: 3.0, hint: '高频请求会触发 HTTP 429 限流，5s 为安全值', ok: true },
                    { id: 'fril', label: 'Fril (Rakuma)', def: '2.0', min: 1.0, hint: '服务器响应慢，2s间隔控制请求密度', ok: true },
                    { id: 'bunjang', label: 'Bunjang', def: '2.0', min: 0.5, hint: '韩国平台，2s 间隔平衡速度与稳定性', ok: true },
                    { id: 'carousell', label: 'Carousell', def: '30.0', min: 5, hint: '持久 Session 复用 Cookie 绕过 Cloudflare，30s 探测', ok: true },
                  ].map(p => {
                    const val = parseFloat(cfg.per_platform_interval[p.id] ?? '')
                    const isTooLow = !isNaN(val) && val > 0 && val < (p.min || 0.3)
                    return (
                      <div key={p.id} className="platform-interval-row" style={{
                        borderColor: isTooLow ? 'var(--warning)' : undefined,
                        background: isTooLow ? 'var(--warning-dim)' : undefined,
                      }}>
                        <span className="platform-interval-label">
                          {isTooLow && '⚠️ '}{p.label}
                        </span>
                        <input type="number"
                               value={cfg.per_platform_interval[p.id] ?? ''}
                               placeholder={p.def}
                               min={0.3} max={3600} step={0.1}
                               onChange={e => setCfg(c => ({
                                 ...c,
                                 per_platform_interval: { ...c.per_platform_interval, [p.id]: e.target.value }
                               }))}
                               className="input" style={{ width: 90, textAlign: 'center' }} />
                        <span className="platform-interval-hint" style={{ color: isTooLow ? 'var(--warning)' : undefined }}>
                          {isTooLow ? `⚠️ 建议不低于 ${p.min}s` : p.hint}
                        </span>
                        <span className="platform-interval-default">默认 {p.def}s</span>
                      </div>
                    )
                  })}
                </div>
                <button onClick={save} className="btn btn-primary" style={{ marginTop: 16 }}>保存间隔</button>
              </div>
            </>
          )}

          {activeTab === 'filter' && (
            <>
              <div className="card">
                <h3 className="set-section-title">🚫 黑名单卖家</h3>
                <div className="set-field">
                  <label>卖家 ID / 用户名（每行一个）</label>
                  <textarea rows={5} value={cfg.seller_blacklist}
                            onChange={e => setCfg(c => ({ ...c, seller_blacklist: e.target.value }))}
                            placeholder={"seller_id_1\nseller_id_2"}
                            className="textarea" />
                </div>
                <p className="set-hint">匹配到的卖家商品将被自动过滤，不推送通知。</p>
                <button onClick={save} className="btn btn-primary">保存黑名单</button>
              </div>

              <div className="card" style={{ marginTop: 20 }}>
                <h3 className="set-section-title">🌏 Carousell 地区</h3>
                <div className="set-field">
                  <label>选择要监控的地区</label>
                  <div className="checkbox-group">
                    {['SG', 'MY', 'HK', 'TW', 'PH', 'ID', 'AU'].map(r => (
                      <label key={r} className="checkbox-label">
                        <input type="checkbox"
                               checked={cfg.carousell_regions.split(',').includes(r)}
                               onChange={e => {
                                 const regions = cfg.carousell_regions.split(',').filter(Boolean)
                                 if (e.target.checked) regions.push(r)
                                 else regions.splice(regions.indexOf(r), 1)
                                 setCfg(c => ({ ...c, carousell_regions: regions.join(',') || 'SG' }))
                               }} />
                        <span>{r}</span>
                      </label>
                    ))}
                  </div>
                </div>
                <p className="set-hint" style={{ color: 'var(--warning)' }}>
                  ⚠️ Carousell 全地区已被 Cloudflare 反爬虫拦截，当前不可用。
                </p>
                <button onClick={save} className="btn btn-primary">保存地区</button>
              </div>
            </>
          )}

          {activeTab === 'monitor' && (
            <div className="card">
              <h3 className="set-section-title">⚡ 监控控制</h3>
              <MonitorControl />
            </div>
          )}
        </div>
      </div>

      {msg && <div className={`toast ${msg.includes('✓') || msg.includes('成功') ? 'success' : 'error'}`}>{msg}</div>}
    </div>
  )
}

function MonitorControl() {
  const [running, setRunning] = useState(false)
  const [loading, setLoading] = useState(false)
  const [turboCfg, setTurboCfg] = useState({
    check_new_enabled: true,
    check_new_interval: '2.0',
    auto_seller_enabled: true,
    auto_seller_max: '50',
    auto_seller_min_hits: '2',
    bff_enabled: false,
    bff_interval: '5.0',
  })

  async function check() {
    const s: any = await monitor.status()
    setRunning(s.running)
    const d: any = await settings.get()
    setTurboCfg({
      check_new_enabled: d.check_new_enabled !== false,
      check_new_interval: String(d.check_new_interval ?? 2.0),
      auto_seller_enabled: d.auto_seller_enabled !== false,
      auto_seller_max: String(d.auto_seller_max ?? 50),
      auto_seller_min_hits: String(d.auto_seller_min_hits ?? 2),
      bff_enabled: d.bff_enabled === true,
      bff_interval: String(d.bff_interval ?? 5.0),
    })
  }

  useEffect(() => { check() }, [])

  async function toggle() {
    setLoading(true)
    try {
      if (running) await monitor.stop()
      else await monitor.start()
      setRunning(!running)
    } finally { setLoading(false) }
  }

  async function saveTurbo() {
    await settings.update({
      check_new_enabled: turboCfg.check_new_enabled,
      check_new_interval: parseFloat(turboCfg.check_new_interval) || 2.0,
      auto_seller_enabled: turboCfg.auto_seller_enabled,
      auto_seller_max: parseInt(turboCfg.auto_seller_max) || 50,
      auto_seller_min_hits: parseInt(turboCfg.auto_seller_min_hits) || 2,
      bff_enabled: turboCfg.bff_enabled,
      bff_interval: parseFloat(turboCfg.bff_interval) || 5.0,
    })
  }

  return (
    <div className="monitor-ctrl">
      <div className="ctrl-info">
        <span className={`ctrl-dot ${running ? 'on' : ''}`} />
        当前状态：<strong>{running ? '运行中' : '已停止'}</strong>
      </div>
      <button onClick={toggle} disabled={loading}
              className={`btn ${running ? 'btn-danger' : 'btn-success'}`}>
        {loading ? '...' : running ? '⏹ 停止监控' : '▶ 启动监控'}
      </button>

      <div style={{ marginTop: 20, borderTop: '1px solid var(--border)', paddingTop: 16 }}>
        <h4 style={{ margin: '0 0 12px', fontSize: 14 }}>🚀 Turbo 提速配置</h4>

        <label className="set-label" style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
          <input type="checkbox" checked={turboCfg.check_new_enabled}
                 onChange={e => setTurboCfg(c => ({ ...c, check_new_enabled: e.target.checked }))} />
          <span>D 提速：check-new-contents 前置检测</span>
          <span style={{ color: 'var(--text3)', fontSize: 12 }}>（无新品时跳过 Feed 拉取，节省请求）</span>
        </label>
        {turboCfg.check_new_enabled && (
          <div style={{ marginLeft: 24, marginBottom: 8 }}>
            <label className="set-label">检测间隔(秒)
              <input type="number" step="0.5" min="1" max="30" value={turboCfg.check_new_interval}
                     onChange={e => setTurboCfg(c => ({ ...c, check_new_interval: e.target.value }))}
                     style={{ width: 70, marginLeft: 8 }} />
            </label>
          </div>
        )}

        <label className="set-label" style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
          <input type="checkbox" checked={turboCfg.auto_seller_enabled}
                 onChange={e => setTurboCfg(c => ({ ...c, auto_seller_enabled: e.target.checked }))} />
          <span>E 提速：自动卖家发现</span>
          <span style={{ color: 'var(--text3)', fontSize: 12 }}>（命中≥N次的卖家自动监控，秒级上新）</span>
        </label>
        {turboCfg.auto_seller_enabled && (
          <div style={{ marginLeft: 24, marginBottom: 8, display: 'flex', gap: 16 }}>
            <label className="set-label">最低命中次数
              <input type="number" min="1" max="20" value={turboCfg.auto_seller_min_hits}
                     onChange={e => setTurboCfg(c => ({ ...c, auto_seller_min_hits: e.target.value }))}
                     style={{ width: 60, marginLeft: 8 }} />
            </label>
            <label className="set-label">最大卖家数
              <input type="number" min="5" max="200" value={turboCfg.auto_seller_max}
                     onChange={e => setTurboCfg(c => ({ ...c, auto_seller_max: e.target.value }))}
                     style={{ width: 60, marginLeft: 8 }} />
            </label>
          </div>
        )}

        <label className="set-label" style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
          <input type="checkbox" checked={turboCfg.bff_enabled}
                 onChange={e => setTurboCfg(c => ({ ...c, bff_enabled: e.target.checked }))} />
          <span>F 提速：BFF App 端点</span>
          <span style={{ color: 'var(--text3)', fontSize: 12 }}>（实验性，components:build 新着数据源）</span>
        </label>
        {turboCfg.bff_enabled && (
          <div style={{ marginLeft: 24, marginBottom: 8 }}>
            <label className="set-label">BFF 间隔(秒)
              <input type="number" step="1" min="3" max="60" value={turboCfg.bff_interval}
                     onChange={e => setTurboCfg(c => ({ ...c, bff_interval: e.target.value }))}
                     style={{ width: 70, marginLeft: 8 }} />
            </label>
          </div>
        )}

        <button onClick={saveTurbo} className="btn btn-primary" style={{ marginTop: 8 }}>保存 Turbo 配置</button>
      </div>
    </div>
  )
}