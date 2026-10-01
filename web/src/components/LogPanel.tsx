import React from 'react'

export default function LogPanel({ logs }: { logs: string[] }) {
  return (
    <div className="log-panel">
      <div className="log-header">
        <span className="log-title">📡 实时日志</span>
        <span className="log-count">{logs.length}</span>
      </div>
      <div className="log-body">
        {logs.length === 0 ? (
          <div className="log-empty">等待监控数据...</div>
        ) : (
          logs.slice(-100).reverse().map((line, i) => (
            <div key={i} className="log-line">{line}</div>
          ))
        )}
      </div>
    </div>
  )
}