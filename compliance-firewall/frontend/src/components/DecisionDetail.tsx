import { motion } from 'framer-motion'
import {
  BadgeDollarSign,
  Ban,
  CalendarDays,
  Cpu,
  Handshake,
  Link2,
  Minus,
  Percent,
  Quote,
  ShieldAlert,
  Timer,
  type LucideIcon,
} from 'lucide-react'
import type { AICall, FactResult, FactType, TraceStep } from '../api/types'
import { Mark } from './ui'

const FACT_ICON: Record<FactType, LucideIcon> = {
  price: BadgeDollarSign,
  percent: Percent,
  period: Timer,
  date: CalendarDays,
  link: Link2,
  promise: Handshake,
  phrase: Ban,
  security: ShieldAlert,
}

const FACT_LABEL: Record<FactType, string> = {
  price: 'Price',
  percent: 'Percent',
  period: 'Time period',
  date: 'Date',
  link: 'Link',
  promise: 'Promise',
  phrase: 'Banned phrase',
  security: 'Security',
}

const SOURCE_LABEL: Record<FactResult['fact']['source'], string> = {
  pattern: 'pattern rule',
  ai: 'AI extraction',
  banned_list: 'banned list',
  security_scan: 'security scan',
}

const STEP_LABEL: Record<string, string> = {
  load_rules: 'Load rules',
  extract: 'Extract facts',
  simulate: 'Simulated failure',
  code_checks: 'Code checks',
  ai_extract: 'AI extraction',
  ai_check: 'AI policy check',
  decide: 'Decision',
  audit: 'Audit log',
}

function tone(result: FactResult): 'ok' | 'bad' | 'skip' {
  if (result.skipped) return 'skip'
  return result.ok ? 'ok' : 'bad'
}

/** The raw AI answer with every extracted fact highlighted by its check result. */
export function RawAnswer({ text, results }: { text: string; results: FactResult[] }) {
  // Stored answers may be PII-redacted, which shifts offsets: only trust spans that still match.
  const spans = results.filter(
    (r) => r.fact.end > r.fact.start && text.slice(r.fact.start, r.fact.end) === r.fact.raw,
  )
  const cuts = [...new Set([0, text.length, ...spans.flatMap((r) => [r.fact.start, r.fact.end])])].sort(
    (a, b) => a - b,
  )

  return (
    <p className="raw-answer">
      {cuts.slice(0, -1).map((start, i) => {
        const end = cuts[i + 1]
        const piece = text.slice(start, end)
        // Facts can nest (a period inside a promise sentence): the most specific one wins.
        const covering = spans
          .filter((r) => r.fact.start <= start && r.fact.end >= end)
          .sort((a, b) => a.fact.end - a.fact.start - (b.fact.end - b.fact.start))
        if (!covering.length) return <span key={start}>{piece}</span>
        const top = covering[0]
        return (
          <mark key={start} className={`hl ${tone(top)} ${top.fact.type === 'promise' ? 'wide' : ''}`} title={top.reason}>
            {piece}
          </mark>
        )
      })}
    </p>
  )
}

export function FactList({ results }: { results: FactResult[] }) {
  if (!results.length) {
    return <p className="muted small">No facts found in this answer: nothing to check.</p>
  }
  return (
    <ul className="facts">
      {results.map((result, i) => {
        const Icon = FACT_ICON[result.fact.type]
        const kind = tone(result)
        return (
          <motion.li
            key={`${result.fact.start}-${result.fact.type}-${i}`}
            className={`fact ${kind}`}
            initial={{ opacity: 0, x: 18 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: 0.05 * i, duration: 0.3 }}
          >
            {kind === 'skip' ? (
              <span className="mark skip">
                <Minus size={14} />
              </span>
            ) : (
              <Mark ok={result.ok} />
            )}
            <div className="fact-body">
              <div className="fact-top">
                <span className="fact-type">
                  <Icon size={13} />
                  {FACT_LABEL[result.fact.type]}
                </span>
                <code className="fact-raw">{result.fact.raw}</code>
                {result.fact.product && <span className="chip tiny">{result.fact.product}</span>}
                <span className="chip tiny dim">{SOURCE_LABEL[result.fact.source]}</span>
              </div>
              <p className="fact-reason">{result.reason || (result.ok ? 'matches the rule' : 'failed')}</p>
              {result.rule && (
                <p className="fact-rule">
                  <span>Rule</span> {result.rule}
                </p>
              )}
              {result.quote && (
                <p className="fact-quote">
                  <Quote size={12} /> {result.quote}
                </p>
              )}
            </div>
          </motion.li>
        )
      })}
    </ul>
  )
}

export function TraceView({ trace }: { trace: TraceStep[] }) {
  return (
    <ol className="trace">
      {trace.map((step, i) => (
        <motion.li
          key={`${step.step}-${i}`}
          className={`trace-step ${step.status}`}
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.06 * i }}
        >
          <span className="trace-dot" />
          <div>
            <div className="trace-name">
              {STEP_LABEL[step.step] ?? step.step}
              <span className="trace-status">{step.status}</span>
              {step.status !== 'skipped' && <span className="trace-ms">{step.ms.toFixed(1)} ms</span>}
            </div>
            {step.note && <div className="trace-note">{step.note}</div>}
          </div>
        </motion.li>
      ))}
    </ol>
  )
}

export function AICalls({ calls }: { calls: AICall[] }) {
  if (!calls.length) {
    return (
      <p className="muted small">
        <Cpu size={13} /> No AI calls: this decision was made by code checks alone.
      </p>
    )
  }
  return (
    <ul className="ai-calls">
      {calls.map((call, i) => (
        <li key={i}>
          <span className={`chip tiny ${call.outcome === 'ok' ? 'ok' : 'warn'}`}>{call.outcome.replace('_', ' ')}</span>
          <strong>{call.purpose}</strong>
          <span className="muted">{call.model}</span>
          <span className="mono">{Math.round(call.ms)} ms</span>
          {call.redactions > 0 && <span className="chip tiny">{call.redactions} redacted</span>}
          {call.error && <span className="ai-call-error">{call.error}</span>}
        </li>
      ))}
    </ul>
  )
}
