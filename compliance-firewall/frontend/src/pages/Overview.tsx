import { animate, motion, useMotionValue, useTransform } from 'framer-motion'
import { ArrowRight, BookLock, FlaskConical, ScrollText, SplitSquareHorizontal, Workflow, type LucideIcon } from 'lucide-react'
import { lazy, Suspense, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import type { GovernanceReport } from '../api/types'
import { Pipeline } from '../components/Pipeline'
import { Panel, TiltCard } from '../components/ui'
import { useStore } from '../store'

// three.js is the heaviest dependency: load it separately so the page paints first
const HeroScene = lazy(() => import('../components/HeroScene').then((module) => ({ default: module.HeroScene })))

const FEATURES: { to: string; icon: LucideIcon; title: string; text: string }[] = [
  {
    to: '/live',
    icon: SplitSquareHorizontal,
    title: 'Side-by-side views',
    text: 'A polished customer chat next to the compliance view: raw answer, every fact with ✓/✗, and a plain-English reason.',
  },
  {
    to: '/rules',
    icon: BookLock,
    title: 'Editable trusted rules',
    text: 'Official prices, policies, allowed links, banned phrases and safe messages, edited through forms and versioned.',
  },
  {
    to: '/audit',
    icon: ScrollText,
    title: 'Audit log',
    text: 'A filterable, colour-coded record of every decision with the rule version used. Re-check any old answer.',
  },
  {
    to: '/suite',
    icon: FlaskConical,
    title: '50-answer test suite',
    text: 'Run all labelled answers in one batch and prove that no rejected answer ever reaches the customer.',
  },
]

function CountUp({ value }: { value: number }) {
  const motionValue = useMotionValue(0)
  const text = useTransform(motionValue, (v) => Math.round(v).toLocaleString())
  useEffect(() => {
    const controls = animate(motionValue, value, { duration: 0.9, ease: 'easeOut' })
    return controls.stop
  }, [motionValue, value])
  return <motion.span>{text}</motion.span>
}

export function Overview() {
  const { health, online } = useStore()
  const [report, setReport] = useState<GovernanceReport | null>(null)

  useEffect(() => {
    if (!online) return
    api.governance().then(setReport, () => setReport(null))
  }, [online])

  const stats = [
    { label: 'Approved', value: report?.decisions.Approved ?? 0, tone: 'ok' },
    { label: 'Rejected', value: report?.decisions.Rejected ?? 0, tone: 'bad' },
    { label: 'Error (failed closed)', value: report?.decisions.Error ?? 0, tone: 'warn' },
    { label: 'Rule versions', value: report?.rules.versions ?? 0, tone: 'accent' },
  ]

  return (
    <div className="stack wide-gap">
      <section className="hero">
        <Suspense fallback={<div className="hero-scene" />}>
          <HeroScene />
        </Suspense>
        <motion.div className="hero-copy" initial={{ opacity: 0, y: 24 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6 }}>
          <span className="eyebrow">Compliance firewall</span>
          <h1>
            No unchecked AI answer
            <br />
            <span className="glow-text">reaches a customer.</span>
          </h1>
          <p>
            Invented prices, discounts, refund terms and links are a legal risk. Every AI answer is intercepted, its facts are
            checked against your trusted rules, and anything wrong is replaced by a pre-approved safe message.
          </p>
          <div className="hero-actions">
            <Link to="/live" className="btn primary big">
              Open the live firewall <ArrowRight size={16} />
            </Link>
            <Link to="/suite" className="btn big">
              Run the 50-answer suite
            </Link>
          </div>
        </motion.div>
      </section>

      <section className="stats">
        {stats.map(({ label, value, tone }, i) => (
          <motion.div key={label} initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.15 + i * 0.07 }}>
            <TiltCard className={`stat ${tone}`}>
              <strong>{report ? <CountUp value={value} /> : '–'}</strong>
              <span>{label}</span>
            </TiltCard>
          </motion.div>
        ))}
      </section>
      {online === false && (
        <p className="error-note">
          The backend is not reachable. Start it from <code>compliance-firewall/backend</code> with{' '}
          <code>uvicorn app.main:app --port 8000</code>.
        </p>
      )}

      <Panel
        title="How an answer is checked"
        icon={<Workflow size={16} />}
        actions={<span className="chip tiny accent">live on rules v{health?.rule_version ?? '–'}</span>}
      >
        <Pipeline />
      </Panel>

      <section className="features">
        {FEATURES.map(({ to, icon: Icon, title, text }) => (
          <Link key={to} to={to} className="feature-link">
            <TiltCard className="feature">
              <span className="feature-icon">
                <Icon size={20} />
              </span>
              <h3>{title}</h3>
              <p>{text}</p>
              <span className="feature-go">
                Open <ArrowRight size={14} />
              </span>
            </TiltCard>
          </Link>
        ))}
      </section>
    </div>
  )
}
