import { AnimatePresence, motion } from 'framer-motion'
import { Activity, BookLock, FlaskConical, LayoutDashboard, ScrollText, ShieldCheck, SplitSquareHorizontal } from 'lucide-react'
import { BrowserRouter, NavLink, Route, Routes, useLocation } from 'react-router-dom'
import { Audit } from './pages/Audit'
import { Governance } from './pages/Governance'
import { Live } from './pages/Live'
import { Overview } from './pages/Overview'
import { RulesPage } from './pages/Rules'
import { Suite } from './pages/Suite'
import { StoreProvider, useStore } from './store'

const NAV = [
  { to: '/', label: 'Overview', icon: LayoutDashboard },
  { to: '/live', label: 'Live firewall', icon: SplitSquareHorizontal },
  { to: '/rules', label: 'Trusted rules', icon: BookLock },
  { to: '/audit', label: 'Audit log', icon: ScrollText },
  { to: '/suite', label: 'Test suite', icon: FlaskConical },
  { to: '/governance', label: 'Governance', icon: Activity },
]

function StatusPill() {
  const { health, online } = useStore()
  if (online === null) return <span className="status-pill">Connecting…</span>
  if (!online) {
    return (
      <span className="status-pill bad" title="Start it with: uvicorn app.main:app --port 8000">
        <i className="pulse-dot" /> Backend offline
      </span>
    )
  }
  return (
    <span className="status-pill ok">
      <i className="pulse-dot" /> Online
      <b>rules v{health?.rule_version ?? '–'}</b>
      <span className={health?.ai_configured ? '' : 'warn-text'}>{health?.ai_configured ? 'AI ready' : 'AI key missing'}</span>
    </span>
  )
}

function Toasts() {
  const { toasts } = useStore()
  return (
    <div className="toasts" aria-live="polite">
      <AnimatePresence>
        {toasts.map((toast) => (
          <motion.div
            key={toast.id}
            className={`toast ${toast.kind}`}
            initial={{ opacity: 0, x: 40 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: 40 }}
          >
            {toast.text}
          </motion.div>
        ))}
      </AnimatePresence>
    </div>
  )
}

function Shell() {
  const location = useLocation()
  return (
    <>
      <div className="backdrop" aria-hidden="true">
        <div className="backdrop-grid" />
        <div className="backdrop-glow a" />
        <div className="backdrop-glow b" />
        <div className="backdrop-glow c" />
        <div className="backdrop-glow d" />
      </div>

      <header className="topbar">
        <NavLink to="/" className="brand">
          <span className="brand-mark">
            <ShieldCheck size={20} />
          </span>
          <span>
            <strong>Compliance Firewall</strong>
            <small>for AI answers</small>
          </span>
        </NavLink>
        <nav className="nav" aria-label="Main">
          {NAV.map(({ to, label, icon: Icon }) => (
            <NavLink key={to} to={to} end={to === '/'} className={({ isActive }) => (isActive ? 'active' : '')}>
              <Icon size={15} />
              <span>{label}</span>
            </NavLink>
          ))}
        </nav>
        <StatusPill />
      </header>

      <main className="page">
        <AnimatePresence mode="wait">
          <motion.div
            key={location.pathname}
            initial={{ opacity: 0, y: 14 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            transition={{ duration: 0.25 }}
          >
            <Routes location={location}>
              <Route path="/" element={<Overview />} />
              <Route path="/live" element={<Live />} />
              <Route path="/rules" element={<RulesPage />} />
              <Route path="/audit" element={<Audit />} />
              <Route path="/suite" element={<Suite />} />
              <Route path="/governance" element={<Governance />} />
              <Route path="*" element={<Overview />} />
            </Routes>
          </motion.div>
        </AnimatePresence>
      </main>
      <Toasts />
    </>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <StoreProvider>
        <Shell />
      </StoreProvider>
    </BrowserRouter>
  )
}
