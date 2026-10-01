import React, { useEffect, useRef, useState } from 'react'
import { useWS } from '../hooks/useWS'

export default function Logs() {
  const [logs, setLogs] = useState<string[]>([])
  const [filter, setFilter] = useState('')
  const bottomRef = useRef<HTMLDivElement>(null)
  const { on } = useWS()

  useEffect(() => {
    const off1 = on('new_item', (item: any) => {
      const t = new Date().toLocaleTimeString()
      setLogs(prev => [...prev, `[${t}] [${item.platform}] 新商品: ${item.name}`].slice(-500))
    })
    const off2 = on('log', (data: any) => {
      const t = new Date().toLocaleTimeString()
      setLogs(prev => [...prev, `[${t}] [${data.platform}] ${data.message}`].slice(-500))
    })
    const off3 = on('monitor_status', (data: any) => {
      const t = new Date().toLocaleTimeString()
      setLogs(prev => [...prev, `[${t}] 监控${data.running ? '已启动' : '已停止'}`].slice(-500))
    })
    return () => { off1(); off2(); off3() }
  }, [on])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [logs])

  const filteredLogs = filter
    ? logs.filter(l => l.toLowerCase().includes(filter.toLowerCase()))
    : logs

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1 className="page-title">📋 运行日志</h1>
          <p className="page-subtitle">实时监控运行日志</p>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <span className="tag">{logs.length} 条</span>
          <button className="btn btn-outline btn-sm" onClick={() => setLogs([])}>清空</button>
        </div>
      </div>

      <div className="logs-search-bar">
        <span className="items-search-icon">🔍</span>
        <input
          type="text"
          placeholder="搜索日志..."
          value={filter}
          onChange={e => setFilter(e.target.value)}
          className="input"
        />
      </div>

      <div className="card log-full-card">
        {filteredLogs.length === 0 ? (
          <div className="empty">
            <div className="empty-icon">📋</div>
            <div className="empty-title">暂无日志</div>
            <div style={{ color: 'var(--text-muted)', fontSize: 13 }}>启动监控后自动记录</div>
          </div>
        ) : (
          filteredLogs.map((l, i) => <div key={i} className="log-line">{l}</div>)
        )}
        <div ref={bottomRef} />
      </div>
    </div>
  )
}