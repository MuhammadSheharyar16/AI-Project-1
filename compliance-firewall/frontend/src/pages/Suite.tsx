import { motion } from 'framer-motion'
import { Check, Cpu, FlaskConical, Play, ShieldCheck, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import { api, ApiError } from '../api/client'
import type { SuiteRow } from '../api/types'
import { DecisionBadge, EmptyState, ErrorNote, Panel, Segmented, TiltCard } from '../components/ui'
import { useStore } from '../store'

type RowFilter = 'all' | 'wrong' | 'reject' | 'approve'

const percent = (rate: number) => `${(rate * 100).toFixed(rate * 100 % 1 ? 1 : 0)}%`

interface MetricProps {
  label: string
  value: string
  target: string
  pass: boolean
  detail: string
  delay: number
}

function Metric({ label, value, target, pass, detail, delay }: MetricProps) {
  return (
    <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay }}>
      <TiltCard className={`metric ${pass ? 'ok' : 'bad'}`}>
        <span className="metric-label">{label}</span>
        <strong className="metric-value">{value}</strong>
        <span className={`chip tiny ${pass ? 'ok' : 'bad'}`}>
          {pass ? <Check size={11} /> : <X size={11} />} target {target}
        </span>
        <span className="muted small">{detail}</span>
      </TiltCard>
    </motion.div>
  )
}

export function Suite() {
  const { suite, setSuite, toast, refreshHealth } = useStore()
  const [running, setRunning] = useState(false)
  const [seconds, setSeconds] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const [filter, setFilter] = useState<RowFilter>('all')

  useEffect(() => {
    if (!running) return
    const started = Date.now()
    const timer = setInterval(() => setSeconds(Math.floor((Date.now() - started) / 1000)), 500)
    return () => clearInterval(timer)
  }, [running])

  const run = async () => {
    setRunning(true)
    setSeconds(0)
    setError(null)
    try {
      const report = await api.runSuite()
      setSuite(report)
      toast(report.leaked === 0 ? 'ok' : 'bad', `Suite finished: ${report.leaked} rejected answers shown to the customer.`)
      void refreshHealth()
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : 'The suite run failed')
    } finally {
      setRunning(false)
    }
  }

  const rejects = suite?.rows.filter((row) => row.label === 'reject') ?? []
  const approves = suite?.rows.filter((row) => row.label === 'approve') ?? []
  const wrong = suite?.rows.filter((row) => !row.correct) ?? []
  const errors = suite?.rows.filter((row) => row.decision === 'Error').length ?? 0
  const rows: SuiteRow[] = !suite
    ? []
    : filter === 'wrong'
      ? wrong
      : filter === 'reject'
        ? rejects
        : filter === 'approve'
          ? approves
          : suite.rows

  return (
    <div className="stack">
      <div className="page-head">
        <div>
          <h1>Test suite</h1>
          <p>50 labelled AI answers (25 should pass, 25 should be blocked), run in one batch on the latest rules.</p>
        </div>
        <button type="button" className="btn primary big" disabled={running} onClick={run}>
          <Play size={16} /> {running ? 'Running…' : suite ? 'Run again' : 'Run all 50 answers'}
        </button>
      </div>

      {error && <ErrorNote message={error} onRetry={run} />}

      {running && (
        <Panel className="suite-running">
          <div className="scan-box wide">
            <div className="scan-line" />
            <FlaskConical size={30} />
          </div>
          <strong>Checking 50 answers… {seconds}s</strong>
          <span className="muted small">
            Answers with promises need a free-tier AI call each, so a full run can take from a few seconds to a couple of minutes. Every result is
            saved to the audit log.
          </span>
          <div className="progress">
            <i />
          </div>
        </Panel>
      )}

      {!suite && !running && !error && (
        <Panel>
          <EmptyState icon={<FlaskConical size={26} />} title="No run yet in this session">
            Targets: 0 rejected answers ever shown to the customer · at least 95% of violations caught · at most 10% of clean
            answers wrongly blocked.
          </EmptyState>
        </Panel>
      )}

      {suite && !running && (
        <>
          <div className="metrics">
            <Metric
              label="Rejected answers shown to customer"
              value={String(suite.leaked)}
              target="0"
              pass={suite.leaked === 0}
              detail={`of ${rejects.length} answers labelled Reject`}
              delay={0}
            />
            <Metric
              label="Violations caught"
              value={percent(suite.caught_rate)}
              target="≥ 95%"
              pass={suite.caught_rate >= 0.95}
              detail={`${rejects.length - suite.leaked} of ${rejects.length} blocked`}
              delay={0.08}
            />
            <Metric
              label="Clean answers wrongly blocked"
              value={percent(suite.false_block_rate)}
              target="≤ 10%"
              pass={suite.false_block_rate <= 0.1}
              detail={`${approves.filter((row) => !row.shown_raw_answer).length} of ${approves.length} blocked`}
              delay={0.16}
            />
          </div>

          <div className={`suite-banner ${suite.leaked === 0 ? 'ok' : 'bad'}`}>
            <ShieldCheck size={20} />
            <span>
              {suite.leaked === 0
                ? 'The customer view never showed an answer labelled Reject.'
                : `${suite.leaked} answer(s) labelled Reject reached the customer view.`}
            </span>
            <span className="chip tiny accent">rules v{suite.rule_version ?? '–'}</span>
            <span className="chip tiny">
              <Cpu size={11} /> {suite.ai_calls} AI calls
            </span>
            {errors > 0 && (
              <span className="chip tiny warn" title="Errors fail closed: the customer got the safe message. Often the free-tier AI call budget.">
                {errors} failed closed (Error)
              </span>
            )}
          </div>

          <Panel
            title="Results"
            icon={<FlaskConical size={16} />}
            className="table-panel"
            actions={
              <Segmented
                label="Filter rows"
                value={filter}
                onChange={setFilter}
                options={[
                  { value: 'all', label: `All ${suite.total}` },
                  { value: 'approve', label: 'Should pass' },
                  { value: 'reject', label: 'Should block' },
                  { value: 'wrong', label: `Mismatches ${wrong.length}`, tone: wrong.length ? 'bad' : 'ok' },
                ]}
              />
            }
          >
            {rows.length === 0 ? (
              <EmptyState icon={<Check size={26} />} title="Nothing here">
                No rows match this filter.
              </EmptyState>
            ) : (
              <div className="table-scroll">
                <table className="audit-table suite-table">
                  <thead>
                    <tr>
                      <th>ID</th>
                      <th>Category</th>
                      <th>Label</th>
                      <th>Decision</th>
                      <th>Customer saw</th>
                      <th>Match</th>
                      <th>Reasons</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((row) => (
                      <tr key={row.id} className={`row static ${row.correct ? '' : 'mismatch'}`}>
                        <td className="mono">{row.id}</td>
                        <td>{row.category.replaceAll('_', ' ')}</td>
                        <td>
                          <span className={`chip tiny ${row.label === 'approve' ? 'ok' : 'bad'}`}>{row.label}</span>
                        </td>
                        <td>
                          <DecisionBadge decision={row.decision} />
                        </td>
                        <td className="nowrap">{row.shown_raw_answer ? 'AI answer' : 'Safe message'}</td>
                        <td>
                          <span className={`mark ${row.correct ? 'ok' : 'bad'}`}>{row.correct ? <Check size={14} /> : <X size={14} />}</span>
                        </td>
                        <td className="reasons">
                          {row.reasons.length ? row.reasons.join(' · ') : <span className="muted">–</span>}
                          {row.audit_id !== null && <small className="muted"> (audit #{row.audit_id})</small>}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Panel>
        </>
      )}
    </div>
  )
}
