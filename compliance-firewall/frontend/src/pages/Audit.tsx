import { AnimatePresence, motion } from 'framer-motion'
import { ArrowRight, ChevronLeft, ChevronRight, Cpu, RefreshCw, ScrollText, Search, ThumbsDown, ThumbsUp, X } from 'lucide-react'
import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { api, ApiError } from '../api/client'
import type { AuditEntry, AuditPage, CheckResponse, DecisionStatus, Review, Source } from '../api/types'
import { AICalls, FactList, RawAnswer, TraceView } from '../components/DecisionDetail'
import { DECISION_CLASS, DecisionBadge, EmptyState, ErrorNote, formatTime, Panel, Segmented, Spinner } from '../components/ui'
import { useStore } from '../store'

const PAGE_SIZE = 20
const REVIEWER_KEY = 'firewall.author'

type DecisionFilter = DecisionStatus | 'all'

export function Audit() {
  const { health } = useStore()
  const [decision, setDecision] = useState<DecisionFilter>('all')
  const [source, setSource] = useState<Source | ''>('')
  const [version, setVersion] = useState('')
  const [search, setSearch] = useState('')
  const [query, setQuery] = useState('') // debounced search
  const [offset, setOffset] = useState(0)
  const [page, setPage] = useState<AuditPage | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [openId, setOpenId] = useState<number | null>(null)

  useEffect(() => {
    const timer = setTimeout(() => {
      setQuery(search.trim())
      setOffset(0)
    }, 300)
    return () => clearTimeout(timer)
  }, [search])

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      setPage(
        await api.audit({
          decision: decision === 'all' ? undefined : decision,
          source: source || undefined,
          version: version ? Number(version) : undefined,
          q: query || undefined,
          limit: PAGE_SIZE,
          offset,
        }),
      )
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : 'Could not load the audit log')
    } finally {
      setLoading(false)
    }
  }, [decision, source, version, query, offset])

  useEffect(() => {
    void load()
  }, [load])

  const filtered = decision !== 'all' || source !== '' || version !== '' || query !== ''
  const last = page ? Math.min(page.offset + page.items.length, page.total) : 0

  return (
    <div className="stack">
      <div className="page-head">
        <div>
          <h1>Audit log</h1>
          <p>Every decision, with the rule version that made it. Nothing reaches a customer without a record here.</p>
        </div>
        <button type="button" className="btn ghost" onClick={load} disabled={loading}>
          {loading ? <Spinner /> : <RefreshCw size={14} />} Refresh
        </button>
      </div>

      <Panel className="filters">
        <Segmented
          label="Decision"
          value={decision}
          onChange={(value) => {
            setDecision(value)
            setOffset(0)
          }}
          options={[
            { value: 'all', label: 'All' },
            { value: 'Approved', label: 'Approved', tone: 'ok' },
            { value: 'Rejected', label: 'Rejected', tone: 'bad' },
            { value: 'Error', label: 'Error', tone: 'warn' },
          ]}
        />
        <label className="field search">
          <Search size={15} />
          <input value={search} maxLength={200} placeholder="Search questions and answers…" onChange={(event) => setSearch(event.target.value)} />
        </label>
        <label className="field">
          <span>Source</span>
          <select
            value={source}
            onChange={(event) => {
              setSource(event.target.value as Source | '')
              setOffset(0)
            }}
          >
            <option value="">Any</option>
            <option value="chat">Chat</option>
            <option value="scenario">Scenario</option>
            <option value="suite">Suite</option>
            <option value="recheck">Re-check</option>
          </select>
        </label>
        <label className="field">
          <span>Rules</span>
          <select
            value={version}
            onChange={(event) => {
              setVersion(event.target.value)
              setOffset(0)
            }}
          >
            <option value="">Any version</option>
            {Array.from({ length: health?.rule_version ?? 0 }, (_, i) => (health?.rule_version ?? 0) - i).map((v) => (
              <option key={v} value={v}>
                v{v}
              </option>
            ))}
          </select>
        </label>
      </Panel>

      {error && <ErrorNote message={error} onRetry={load} />}

      <Panel className="table-panel">
        {page && page.items.length === 0 ? (
          <EmptyState icon={<ScrollText size={26} />} title={filtered ? 'No decisions match these filters' : 'No decisions yet'}>
            {filtered ? 'Try widening the filters.' : 'Run a check on the Live firewall page and it will appear here.'}
          </EmptyState>
        ) : (
          <div className="table-scroll">
            <table className="audit-table">
              <thead>
                <tr>
                  <th>#</th>
                  <th>Time</th>
                  <th>Decision</th>
                  <th>Raw AI answer</th>
                  <th>Rules</th>
                  <th>Source</th>
                  <th>AI</th>
                  <th className="num">Latency</th>
                </tr>
              </thead>
              <tbody>
                {page?.items.map((entry) => (
                  <tr
                    key={entry.id}
                    className={`row ${DECISION_CLASS[entry.decision]}`}
                    tabIndex={0}
                    onClick={() => setOpenId(entry.id)}
                    onKeyDown={(event) => event.key === 'Enter' && setOpenId(entry.id)}
                  >
                    <td className="mono">{entry.id}</td>
                    <td className="nowrap muted">{formatTime(entry.created_at)}</td>
                    <td>
                      <DecisionBadge decision={entry.decision} />
                    </td>
                    <td className="answer-cell">
                      <span>{entry.raw_answer}</span>
                      {entry.question && <small>Q: {entry.question}</small>}
                    </td>
                    <td>
                      <span className="version-badge small">v{entry.rule_version ?? '–'}</span>
                    </td>
                    <td className="nowrap">
                      {entry.source}
                      {entry.recheck_of !== null && <small className="muted"> of #{entry.recheck_of}</small>}
                    </td>
                    <td>{entry.ai_used ? <Cpu size={14} className="accent-text" aria-label="AI used" /> : <span className="muted">–</span>}</td>
                    <td className="num mono">{entry.latency_ms} ms</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {page && page.total > 0 && (
          <footer className="pager">
            <span className="muted small">
              {page.offset + 1}–{last} of {page.total}
            </span>
            <button type="button" className="btn ghost small" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>
              <ChevronLeft size={14} /> Newer
            </button>
            <button type="button" className="btn ghost small" disabled={last >= page.total} onClick={() => setOffset(offset + PAGE_SIZE)}>
              Older <ChevronRight size={14} />
            </button>
          </footer>
        )}
      </Panel>

      <AnimatePresence>
        {openId !== null && <Drawer key="drawer" id={openId} onClose={() => setOpenId(null)} onOpen={setOpenId} onChanged={load} />}
      </AnimatePresence>
    </div>
  )
}

interface DrawerProps {
  id: number
  onClose: () => void
  onOpen: (id: number) => void
  onChanged: () => void
}

function Drawer({ id, onClose, onOpen, onChanged }: DrawerProps) {
  const { toast, refreshHealth, health } = useStore()
  const [entry, setEntry] = useState<AuditEntry | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [rechecking, setRechecking] = useState(false)
  const [recheck, setRecheck] = useState<CheckResponse | null>(null)
  const [reviewer, setReviewer] = useState(() => localStorage.getItem(REVIEWER_KEY) ?? '')
  const [reviewNote, setReviewNote] = useState('')
  const [verdict, setVerdict] = useState<Review['verdict']>('agree')
  const [reviewing, setReviewing] = useState(false)

  useEffect(() => {
    setEntry(null)
    setError(null)
    setRecheck(null)
    api
      .auditEntry(id)
      .then(setEntry)
      .catch((caught) => setError(caught instanceof ApiError ? caught.message : 'Could not load this entry'))
  }, [id])

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => event.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const runRecheck = async () => {
    setRechecking(true)
    try {
      setRecheck(await api.recheck(id))
      onChanged()
      void refreshHealth()
    } catch (caught) {
      toast('bad', caught instanceof ApiError ? caught.message : 'Re-check failed')
    } finally {
      setRechecking(false)
    }
  }

  const submitReview = async (event: FormEvent) => {
    event.preventDefault()
    const name = reviewer.trim()
    if (!name || !entry) return
    setReviewing(true)
    try {
      const review = await api.review(id, name, verdict, reviewNote.trim())
      localStorage.setItem(REVIEWER_KEY, name)
      setEntry({ ...entry, reviews: [...entry.reviews, review] })
      setReviewNote('')
      toast('ok', 'Review recorded.')
    } catch (caught) {
      toast('bad', caught instanceof ApiError ? caught.message : 'Could not save the review')
    } finally {
      setReviewing(false)
    }
  }

  return (
    <>
      <motion.div className="scrim" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={onClose} />
      <motion.aside
        className="drawer"
        role="dialog"
        aria-label={`Audit entry ${id}`}
        initial={{ x: '100%' }}
        animate={{ x: 0 }}
        exit={{ x: '100%' }}
        transition={{ type: 'spring', stiffness: 320, damping: 34 }}
      >
        <header className="drawer-head">
          <h2>
            Audit entry <span className="mono">#{id}</span>
          </h2>
          <button type="button" className="icon-btn" aria-label="Close" onClick={onClose}>
            <X size={18} />
          </button>
        </header>

        {error && <ErrorNote message={error} />}
        {!entry && !error && (
          <div className="loading">
            <Spinner size={20} /> Loading…
          </div>
        )}
        {entry && (
          <div className="drawer-body">
            <div className={`verdict ${DECISION_CLASS[entry.decision]}`}>
              <DecisionBadge decision={entry.decision} large />
              <div className="verdict-meta">
                <span className="chip tiny accent">rules v{entry.rule_version ?? '–'}</span>
                <span className="chip tiny">{entry.source}</span>
                <span className="chip tiny">{entry.latency_ms} ms</span>
                <span className="chip tiny">{formatTime(entry.created_at)}</span>
                {entry.recheck_of !== null && (
                  <button type="button" className="chip tiny action" onClick={() => onOpen(entry.recheck_of!)}>
                    re-check of #{entry.recheck_of}
                  </button>
                )}
              </div>
            </div>

            {entry.question && (
              <p className="drawer-question">
                <span>Question</span> {entry.question}
              </p>
            )}

            <div className="side-by-side">
              <div>
                <h3>Customer saw</h3>
                <p className="customer-saw">{entry.shown_to_customer}</p>
              </div>
              <div>
                <h3>Raw AI answer</h3>
                <RawAnswer text={entry.raw_answer} results={entry.results} />
              </div>
            </div>
            {entry.error && (
              <p className="error-note">
                <strong>Check failed:</strong> {entry.error}
              </p>
            )}

            <div className="recheck-box">
              <div>
                <strong>Re-check on the latest rules</strong>
                <p className="muted small">
                  Runs this same answer against rules v{health?.rule_version ?? '–'} and saves a new audit entry. The original
                  stays unchanged.
                </p>
              </div>
              <button type="button" className="btn" disabled={rechecking} onClick={runRecheck}>
                {rechecking ? <Spinner /> : <RefreshCw size={14} />} Re-check
              </button>
            </div>
            {recheck && (
              <motion.div className="recheck-result" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}>
                <div className="recheck-flow">
                  <span>
                    <DecisionBadge decision={entry.decision} />
                    <small>rules v{entry.rule_version ?? '–'}</small>
                  </span>
                  <ArrowRight size={18} />
                  <span>
                    <DecisionBadge decision={recheck.compliance.decision} />
                    <small>rules v{recheck.compliance.rule_version ?? '–'}</small>
                  </span>
                </div>
                <p>
                  {recheck.compliance.decision === entry.decision ? 'The decision is unchanged' : 'The decision changed'} on rules v
                  {recheck.compliance.rule_version}.
                  {recheck.compliance.audit_id !== null && (
                    <>
                      {' '}
                      <button type="button" className="link-btn" onClick={() => onOpen(recheck.compliance.audit_id!)}>
                        Open new entry #{recheck.compliance.audit_id}
                      </button>
                    </>
                  )}
                </p>
              </motion.div>
            )}

            <h3>
              Extracted facts <span className="count">{entry.results.length}</span>
            </h3>
            <FactList results={entry.results} />

            <h3>Pipeline trace</h3>
            <TraceView trace={entry.trace} />

            <h3>AI calls {entry.ai_model && <span className="muted small">· prompt {entry.prompt_version}</span>}</h3>
            <AICalls calls={entry.ai_calls} />

            <h3>
              Human review <span className="count">{entry.reviews.length}</span>
            </h3>
            {entry.reviews.length > 0 && (
              <ul className="reviews">
                {entry.reviews.map((review) => (
                  <li key={review.id} className={review.verdict}>
                    {review.verdict === 'agree' ? <ThumbsUp size={14} /> : <ThumbsDown size={14} />}
                    <div>
                      <strong>{review.reviewer}</strong> {review.verdict === 'agree' ? 'agreed' : 'disagreed'}
                      <span className="muted small"> · {formatTime(review.created_at)}</span>
                      {review.note && <p>{review.note}</p>}
                    </div>
                  </li>
                ))}
              </ul>
            )}
            <form className="review-form" onSubmit={submitReview}>
              <Segmented
                label="Verdict"
                value={verdict}
                onChange={setVerdict}
                options={[
                  { value: 'agree', label: 'Agree', tone: 'ok' },
                  { value: 'disagree', label: 'Disagree', tone: 'bad' },
                ]}
              />
              <input value={reviewer} maxLength={100} placeholder="Your name" aria-label="Reviewer name" onChange={(event) => setReviewer(event.target.value)} />
              <input value={reviewNote} maxLength={1000} placeholder="Note (optional)" aria-label="Review note" onChange={(event) => setReviewNote(event.target.value)} />
              <button type="submit" className="btn" disabled={reviewing || !reviewer.trim()}>
                {reviewing ? <Spinner /> : null} Add review
              </button>
            </form>
          </div>
        )}
      </motion.aside>
    </>
  )
}
