import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { api } from './api/client'
import type { CheckResponse, Health, SuiteReport } from './api/types'

/** One question → intercepted answer, shown in both the customer and the compliance view. */
export interface Exchange {
  id: number
  question: string
  label: string | null // scenario name, when it came from the scenario runner
  pending: boolean
  response: CheckResponse | null
  error: string | null
}

export interface Toast {
  id: number
  kind: 'ok' | 'bad' | 'info'
  text: string
}

interface Store {
  health: Health | null
  online: boolean | null // null until the first health check returns
  refreshHealth: () => Promise<void>
  toasts: Toast[]
  toast: (kind: Toast['kind'], text: string) => void
  exchanges: Exchange[]
  setExchanges: React.Dispatch<React.SetStateAction<Exchange[]>>
  suite: SuiteReport | null
  setSuite: (report: SuiteReport | null) => void
}

const StoreContext = createContext<Store | null>(null)

export function StoreProvider({ children }: { children: ReactNode }) {
  const [health, setHealth] = useState<Health | null>(null)
  const [online, setOnline] = useState<boolean | null>(null)
  const [toasts, setToasts] = useState<Toast[]>([])
  const [exchanges, setExchanges] = useState<Exchange[]>([])
  const [suite, setSuite] = useState<SuiteReport | null>(null)
  const nextToast = useRef(1)

  const refreshHealth = useCallback(async () => {
    try {
      setHealth(await api.health())
      setOnline(true)
    } catch {
      setOnline(false)
    }
  }, [])

  useEffect(() => {
    void refreshHealth()
    const timer = setInterval(() => void refreshHealth(), 10_000)
    return () => clearInterval(timer)
  }, [refreshHealth])

  const toast = useCallback((kind: Toast['kind'], text: string) => {
    const id = nextToast.current++
    setToasts((list) => [...list, { id, kind, text }])
    setTimeout(() => setToasts((list) => list.filter((t) => t.id !== id)), 5000)
  }, [])

  const value = useMemo(
    () => ({ health, online, refreshHealth, toasts, toast, exchanges, setExchanges, suite, setSuite }),
    [health, online, refreshHealth, toasts, toast, exchanges, suite],
  )
  return <StoreContext.Provider value={value}>{children}</StoreContext.Provider>
}

export function useStore(): Store {
  const store = useContext(StoreContext)
  if (!store) throw new Error('useStore must be used inside StoreProvider')
  return store
}
