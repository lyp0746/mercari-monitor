import React, { useEffect, useState } from 'react'
import { auth } from '../api/client'

export default function Login({ onLogin }: { onLogin: () => void }) {
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [needsSetup, setNeedsSetup] = useState(false)

  useEffect(() => {
    auth.status().then((s: any) => {
      if (!s.enabled) {
        setNeedsSetup(true)
        setMode('register')
      }
    }).catch(() => {})
  }, [])

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const fn = mode === 'login' ? auth.login : auth.register
      const res = await fn(username, password)
      localStorage.setItem('auth_token', res.token)
      localStorage.setItem('auth_user', res.username)
      onLogin()
    } catch (err: any) {
      setError(err.message || '操作失败')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="login-page">
      <div className="login-card">
        <div className="login-logo">🛒</div>
        <h1 className="login-title">煤炉助手</h1>
        <p className="login-subtitle">
          {needsSetup ? '首次使用，请创建管理员账号' : '🇯🇵 日本好物，一键直达'}
        </p>

        <form onSubmit={handleSubmit} className="login-form">
          <div className="login-field">
            <label>用户名</label>
            <input
              type="text"
              placeholder="请输入用户名"
              value={username}
              onChange={e => setUsername(e.target.value)}
              className="input"
              autoFocus
            />
          </div>
          <div className="login-field">
            <label>密码</label>
            <input
              type="password"
              placeholder="请输入密码"
              value={password}
              onChange={e => setPassword(e.target.value)}
              className="input"
            />
          </div>
          {error && <div className="login-error">{error}</div>}
          <button type="submit" disabled={loading || !username || !password}
                  className="btn btn-primary btn-lg login-btn">
            {loading ? '...' : needsSetup ? '创建账号' : mode === 'login' ? '登录' : '注册'}
          </button>
        </form>

        {!needsSetup && (
          <div className="login-switch">
            {mode === 'login' ? (
              <span>没有账号？<a onClick={() => setMode('register')}>注册</a></span>
            ) : (
              <span>已有账号？<a onClick={() => setMode('login')}>登录</a></span>
            )}
          </div>
        )}
      </div>
    </div>
  )
}