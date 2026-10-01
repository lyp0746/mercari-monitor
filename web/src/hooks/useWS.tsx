import React, { createContext, useContext, useEffect, useRef, useState, useCallback } from 'react'

type EventHandler = (data: any) => void

interface WSContextValue {
  connected: boolean
  on: (event: string, handler: EventHandler) => () => void
}

const WSContext = createContext<WSContextValue>({ connected: false, on: () => () => {} })

export function WebSocketProvider({ url, children }: { url: string; children: React.ReactNode }) {
  const wsRef = useRef<WebSocket | null>(null)
  const [connected, setConnected] = useState(false)
  const handlersRef = useRef<Map<string, Set<EventHandler>>>(new Map())
  const retryRef = useRef(0)
  const timerRef = useRef<ReturnType<typeof setTimeout>>()

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return

    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:'
    const ws = new WebSocket(`${protocol}//${location.host}${url}`)
    wsRef.current = ws

    ws.onopen = () => {
      setConnected(true)
      retryRef.current = 0
    }

    ws.onclose = () => {
      setConnected(false)
      wsRef.current = null
      const delay = Math.min(1000 * Math.pow(2, retryRef.current), 30000)
      retryRef.current += 1
      timerRef.current = setTimeout(connect, delay)
    }

    ws.onmessage = (e) => {
      try {
        const msg = JSON.parse(e.data)
        const hs = handlersRef.current.get(msg.type)
        if (hs) hs.forEach(h => h(msg.data))
      } catch {}
    }

    const pingInterval = setInterval(() => {
      if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: 'ping' }))
    }, 30000)

    const cleanup = () => {
      clearInterval(pingInterval)
      ws.onclose = null
      ws.close()
    }
    ;(ws as any).__cleanup = cleanup
  }, [url])

  const on = useCallback((event: string, handler: EventHandler) => {
    if (!handlersRef.current.has(event)) handlersRef.current.set(event, new Set())
    handlersRef.current.get(event)!.add(handler)
    return () => { handlersRef.current.get(event)?.delete(handler) }
  }, [])

  useEffect(() => {
    connect()
    return () => {
      clearTimeout(timerRef.current)
      const ws = wsRef.current
      if (ws) {
        const cleanup = (ws as any).__cleanup
        if (cleanup) cleanup()
        else { ws.onclose = null; ws.close() }
      }
    }
  }, [connect])

  return (
    <WSContext.Provider value={{ connected, on }}>
      {children}
    </WSContext.Provider>
  )
}

export function useWS() {
  return useContext(WSContext)
}