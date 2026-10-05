import { motion } from 'framer-motion'
import { Activity, Coins, Cpu, Lock, RefreshCw, ShieldAlert, UserCheck } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { api, ApiError } from '../api/client'
import type { DecisionStatus, GovernanceReport } from '../api/types'
import { DECISION_CLASS, ErrorNote, Panel, Spinner } from '../components/ui'

const DECISIONS: DecisionStatus[] = ['Approved', 'Rejected', 'Error']

const RESOURCES = [
  { name: 'Groq API (free tier)', use: 'AI fact extraction and promise checks', limit: 'Rate-limited; the app caps itself below the limit' },
  { name: 'FastAPI + Python', use: 'Firewall pipeline and HTTP API', limit: 'Open source, runs locally' },
  { name: 'SQLite', use: 'Rules versions and the audit log', limit: 'A local file; no server' },
  { name: 'React + Vite + three.js', use: 'This web app', limit: 'Open source, runs locally' },
]

function Bars({ data, tones }: { data: [string, number][]; tones?: Record<string, string> }) {
  const max = Math.max(1, ...data.map(([, count]) => count))
  if (!data.length) return <p className="muted small">No data yet.</p>
  return (
    <ul className="bars">
      {data.map(([label, count]) => (
        <li key={label}>
          <span className="bar-label">{label.replaceAll('_', ' ')}</span>
          <span className="bar-track">
            <motion.i
              className={tones?.[label] ?? 'accent'}
              initial={{ width: 0 }}
              animate={{ width: `${(count / max) * 100}%` }}
              transition={{ duration: 0.7, ease: 'easeOut' }}
            />
          </span>
          <span className="bar-value mono">{count}</span>
        </li>
      ))}
    </ul>
  )
}

export function Governance() {
  const [report, setReport] = useState<GovernanceReport | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      setReport(await api.governance())
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : 'Could not load the report')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  return (
    <div className="stack">
      <div className="page-head">
        <div>
          <h1>Governance, resources &amp; limits</h1>
          <p>What the AI is allowed to do, what protects it, and what it all costs: $0.</p>
        </div>
        <button type="button" className="btn ghost" onClick={load} disabled={loading}>
          {loading ? <Spinner /> : <RefreshCw size={14} />} Refresh
        </button>
      </div>

      {error && <ErrorNote message={error} onRetry={load} />}
      {!report && !error && (
        <div className="loading">
          <Spinner size={22} /> Loading report…
        </div>
      )}

      {report && (
        <>
          <div className="gov-grid">
            <Panel title="AI configuration" icon={<Cpu size={16} />}>
              <dl className="kv">
                <dt>Provider</dt>
                <dd>{report.ai.provider}</dd>
                <dt>Model</dt>
                <dd className="mono">{report.ai.model}</dd>
                <dt>Prompt version</dt>
                <dd className="mono">{report.ai.prompt_version}</dd>
                <dt>Kill switch</dt>
                <dd>
                  <span className={`chip tiny ${report.ai.enabled ? 'ok' : 'bad'}`}>{report.ai.enabled ? 'AI enabled' : 'AI disabled'}</span>
                </dd>
                <dt>Temperature</dt>
                <dd className="mono">{report.ai.temperature}</dd>
                <dt>Output</dt>
                <dd>{report.ai.json_mode ? 'JSON mode, schema-validated' : 'free text'}</dd>
                <dt>Timeout per call</dt>
                <dd className="mono">{report.ai.timeout_s} s</dd>
                <dt>Call budget</dt>
                <dd className="mono">{report.ai.max_calls_per_minute} / minute</dd>
              </dl>
              <p className="muted small">The AI is used for: {report.ai.uses.join('; ')}.</p>
            </Panel>

            <Panel title="Decisions" icon={<Activity size={16} />}>
              <Bars data={DECISIONS.map((d) => [d, report.decisions[d] ?? 0])} tones={DECISION_CLASS} />
              <h3>AI calls by outcome</h3>
              <Bars data={Object.entries(report.ai_usage.calls_by_outcome)} tones={{ ok: 'ok' }} />
              <h3>AI calls by purpose</h3>
              <Bars data={Object.entries(report.ai_usage.calls_by_purpose)} />
              <p className="muted small">
                Average AI call: {report.ai_usage.avg_call_ms ? `${Math.round(report.ai_usage.avg_call_ms)} ms` : '–'} ·{' '}
                {report.ai_usage.window}
              </p>
            </Panel>

            <Panel title="Human review" icon={<UserCheck size={16} />}>
              <div className="review-stats">
                <div>
                  <strong>{report.human_review.reviews}</strong>
                  <span>reviews</span>
                </div>
                <div className="ok">
                  <strong>{report.human_review.agree}</strong>
                  <span>agreed</span>
                </div>
                <div className="bad">
                  <strong>{report.human_review.disagree}</strong>
                  <span>disagreed</span>
                </div>
              </div>
              <p className="muted small">
                Disagreement rate: {(report.human_review.disagreement_rate * 100).toFixed(1)}%. Reviews are append-only and
                never change a recorded decision. Add one from any entry in the audit log.
              </p>
              <h3>Rules</h3>
              <dl className="kv">
                <dt>Live version</dt>
                <dd>
                  <span className="version-badge small">v{report.rules.latest_version ?? '–'}</span>
                </dd>
                <dt>Last changed by</dt>
                <dd>{report.rules.latest_author ?? 'unknown'}</dd>
                <dt>Versions kept</dt>
                <dd className="mono">{report.rules.versions}</dd>
              </dl>
            </Panel>
          </div>

          <Panel title="Free resources only: $0 spent" icon={<Coins size={16} />}>
            <div className="table-scroll">
              <table className="audit-table resources">
                <thead>
                  <tr>
                    <th>Resource</th>
                    <th>Used for</th>
                    <th>Limit</th>
                  </tr>
                </thead>
                <tbody>
                  {RESOURCES.map((resource) => (
                    <tr key={resource.name} className="row static">
                      <td>
                        <strong>{resource.name}</strong>
                      </td>
                      <td>{resource.use}</td>
                      <td className="muted">{resource.limit}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="muted small">
              App-enforced limits: {report.ai.max_calls_per_minute} AI calls per minute, {report.ai.timeout_s} s per AI call. Going
              over either fails closed: the customer gets the safe message and the audit decision is Error.
            </p>
          </Panel>

          <Panel title="Security controls in force" icon={<Lock size={16} />}>
            <ul className="controls">
              {report.security_controls.map((control, i) => {
                const warning = control.startsWith('WARNING')
                return (
                  <motion.li
                    key={control}
                    className={warning ? 'warn' : ''}
                    initial={{ opacity: 0, x: -10 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: i * 0.03 }}
                  >
                    {warning ? <ShieldAlert size={15} /> : <Lock size={15} />}
                    <span>{control}</span>
                  </motion.li>
                )
              })}
            </ul>
          </Panel>
        </>
      )}
    </div>
  )
}
