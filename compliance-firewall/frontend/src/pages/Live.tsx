import { AnimatePresence, motion } from 'framer-motion'
import {
  Bot,
  Cpu,
  Eye,
  FlaskConical,
  Hash,
  MessageSquare,
  Play,
  Radar,
  ScanSearch,
  Send,
  ShieldCheck,
  Timer,
  Trash2,
  User,
} from 'lucide-react'
import { useEffect, useRef, useState, type FormEvent, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { api, ApiError } from '../api/client'
import type { ChatMode, CheckResponse } from '../api/types'
import { AICalls, FactList, RawAnswer, TraceView } from '../components/DecisionDetail'
import { DecisionBadge, EmptyState, Panel, Segmented } from '../components/ui'
import { QUICK_QUESTIONS, SCENARIOS, type Scenario } from '../scenarios'
import { useStore, type Exchange } from '../store'

const GROUPS = ['Success', 'Edge', 'Bad / abuse'] as const
const GROUP_TONE = { Success: 'ok', Edge: 'info', 'Bad / abuse': 'bad' }
const URL_PATTERN = /(https?:\/\/[^\s]+[^\s.,;:!?)])/g

function linkify(text: string): ReactNode[] {
  return text.split(URL_PATTERN).map((part, i) =>
    i % 2 ? (
      <a key={i} href={part} target="_blank" rel="noreferrer">
        {part}
      </a>
    ) : (
      part
    ),
  )
}

let nextExchangeId = 1

export function Live() {
  const { exchanges, setExchanges, health, refreshHealth } = useStore()
  const [selectedId, setSelectedId] = useState<number | null>(exchanges.at(-1)?.id ?? null)
  const [mode, setMode] = useState<ChatMode>('accurate')
  const [question, setQuestion] = useState('')
  const [draft, setDraft] = useState('')
  const chatRef = useRef<HTMLDivElement>(null)

  const busy = exchanges.some((exchange) => exchange.pending)
  const selected = exchanges.find((exchange) => exchange.id === selectedId) ?? null
  const simulateLocked = health !== null && !health.debug

  useEffect(() => {
    chatRef.current?.scrollTo({ top: chatRef.current.scrollHeight, behavior: 'smooth' })
  }, [exchanges])

  const run = async (questionText: string, label: string | null, call: () => Promise<CheckResponse>) => {
    const id = nextExchangeId++
    setExchanges((list) => [...list, { id, question: questionText, label, pending: true, response: null, error: null }])
    setSelectedId(id)
    const patch = (change: Partial<Exchange>) =>
      setExchanges((list) => list.map((exchange) => (exchange.id === id ? { ...exchange, pending: false, ...change } : exchange)))
    try {
      patch({ response: await call() })
    } catch (error) {
      patch({ error: error instanceof ApiError ? error.message : 'Unexpected error' })
    }
    void refreshHealth()
  }

  const ask = (text: string) => {
    const trimmed = text.trim()
    if (!trimmed || busy) return
    setQuestion('')
    void run(trimmed, null, () => api.chat(trimmed, mode))
  }

  const runScenario = (scenario: Scenario) => {
    if (busy) return
    void run(scenario.question, scenario.title, () => api.check(scenario.answer, scenario.question, scenario.simulate))
  }

  const checkDraft = (event: FormEvent) => {
    event.preventDefault()
    const answer = draft.trim()
    if (!answer || busy) return
    setDraft('')
    void run('(pasted AI answer)', 'Custom answer', () => api.check(answer))
  }

  return (
    <div className="stack">
      <div className="page-head">
        <div>
          <h1>Live firewall</h1>
          <p>Every AI answer is checked before the customer sees it. Left is what the customer sees; right is what compliance sees.</p>
        </div>
        {exchanges.length > 0 && (
          <button
            type="button"
            className="btn ghost"
            disabled={busy}
            onClick={() => {
              setExchanges([])
              setSelectedId(null)
            }}
          >
            <Trash2 size={14} /> Clear session
          </button>
        )}
      </div>

      <Panel title="Client test cases" icon={<FlaskConical size={16} />} className="scenarios">
        <div className="scenario-groups">
          {GROUPS.map((group) => (
            <div key={group} className="scenario-group">
              <span className={`group-label ${GROUP_TONE[group]}`}>{group}</span>
              <div className="chips">
                {SCENARIOS.filter((scenario) => scenario.group === group).map((scenario) => {
                  const locked = scenario.simulate !== undefined && simulateLocked
                  return (
                    <button
                      key={scenario.id}
                      type="button"
                      className={`chip action ${GROUP_TONE[group]}`}
                      disabled={busy || locked}
                      title={
                        locked
                          ? 'Needs DEBUG=true on the backend'
                          : `AI answer: "${scenario.answer}"\nExpected: ${scenario.expected}`
                      }
                      onClick={() => runScenario(scenario)}
                    >
                      <Play size={11} /> {scenario.title}
                    </button>
                  )
                })}
              </div>
            </div>
          ))}
        </div>
        {simulateLocked && (
          <p className="warn-text small scenario-foot" role="note">
            “Checker crashes” and “Checker times out” are switched off: set <code>DEBUG=true</code> in <code>backend/.env</code> and
            restart the backend to demo them.
          </p>
        )}
        <p className="muted small scenario-foot">
          Two more cases live on other pages: edit a price in <Link to="/rules">Trusted rules</Link>, then re-check an old answer
          from the <Link to="/audit">Audit log</Link>; and run all 50 labelled answers in the <Link to="/suite">Test suite</Link>.
        </p>
      </Panel>

      <div className="split">
        <Panel
          title="Customer view"
          icon={<MessageSquare size={16} />}
          className="customer"
          actions={
            <Segmented
              label="Assistant behaviour"
              value={mode}
              onChange={setMode}
              options={[
                { value: 'accurate', label: 'Accurate AI', tone: 'ok' },
                { value: 'mistakes', label: 'AI makes mistakes', tone: 'bad' },
              ]}
            />
          }
        >
          <div className="chat" ref={chatRef}>
            {exchanges.length === 0 && (
              <EmptyState icon={<Bot size={26} />} title="Hisaab Pro assistant">
                Ask a question, or run a test case above. Whatever appears here has passed the firewall.
              </EmptyState>
            )}
            {exchanges.map((exchange) => (
              <div key={exchange.id} className="exchange">
                <motion.div className="bubble-row user" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}>
                  <div className="bubble user">{exchange.question}</div>
                  <span className="avatar user">
                    <User size={14} />
                  </span>
                </motion.div>
                <motion.div
                  className="bubble-row bot"
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: 0.1 }}
                >
                  <span className="avatar bot">
                    <Bot size={14} />
                  </span>
                  {/* A div, not a button: the answer can contain links, which may not nest inside a button. */}
                  <div
                    className={`bubble bot ${exchange.id === selectedId ? 'selected' : ''}`}
                    tabIndex={0}
                    title="Show this answer in the compliance view"
                    onClick={() => setSelectedId(exchange.id)}
                    onKeyDown={(event) => {
                      if (event.target !== event.currentTarget || (event.key !== 'Enter' && event.key !== ' ')) return
                      event.preventDefault()
                      setSelectedId(exchange.id)
                    }}
                  >
                    {exchange.pending ? (
                      <span className="typing">
                        <i />
                        <i />
                        <i />
                      </span>
                    ) : exchange.response ? (
                      linkify(exchange.response.customer.text)
                    ) : (
                      <span className="muted">The assistant is unavailable right now. Nothing was shown.</span>
                    )}
                  </div>
                </motion.div>
              </div>
            ))}
          </div>

          <div className="chips quick">
            {QUICK_QUESTIONS.map((text) => (
              <button key={text} type="button" className="chip action" disabled={busy} onClick={() => ask(text)}>
                {text}
              </button>
            ))}
          </div>
          <form
            className="composer"
            onSubmit={(event) => {
              event.preventDefault()
              ask(question)
            }}
          >
            <input
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              placeholder="Ask the assistant…"
              maxLength={2000}
              aria-label="Your question"
            />
            <button type="submit" className="btn primary" disabled={busy || !question.trim()}>
              <Send size={15} /> Send
            </button>
          </form>
        </Panel>

        <Panel title="Compliance view" icon={<Eye size={16} />} className="compliance">
          <AnimatePresence mode="wait">
            <motion.div
              key={selected ? `${selected.id}-${selected.pending}` : 'none'}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.18 }}
            >
              <ComplianceBody exchange={selected} />
            </motion.div>
          </AnimatePresence>

          <form className="draft-form" onSubmit={checkDraft}>
            <label htmlFor="draft">Check your own AI answer</label>
            <div className="draft-row">
              <textarea
                id="draft"
                rows={2}
                value={draft}
                maxLength={5000}
                onChange={(event) => setDraft(event.target.value)}
                placeholder='e.g. "Pro is only $39 this week, with a lifetime free upgrade!"'
              />
              <button type="submit" className="btn" disabled={busy || !draft.trim()}>
                <ScanSearch size={15} /> Check
              </button>
            </div>
          </form>
        </Panel>
      </div>
    </div>
  )
}

function ComplianceBody({ exchange }: { exchange: Exchange | null }) {
  if (!exchange) {
    return (
      <EmptyState icon={<Radar size={26} />} title="Waiting for an answer">
        The raw AI answer, every extracted fact with ✓/✗ against its rule, and the reason for the decision appear here.
      </EmptyState>
    )
  }
  if (exchange.pending) {
    return (
      <div className="scanning">
        <div className="scan-box">
          <div className="scan-line" />
          <ShieldCheck size={34} />
        </div>
        <strong>Checking the AI answer…</strong>
        <span className="muted small">extract facts → code checks → AI policy check → decision</span>
      </div>
    )
  }
  if (!exchange.response) {
    return (
      <div className="error-note" role="alert">
        {exchange.error} Nothing was shown to the customer.
      </div>
    )
  }

  const { compliance, customer } = exchange.response
  const approved = compliance.decision === 'Approved'
  return (
    <div className="compliance-body">
      <div className={`verdict ${approved ? 'ok' : compliance.decision === 'Rejected' ? 'bad' : 'warn'}`}>
        <DecisionBadge decision={compliance.decision} large />
        <div className="verdict-meta">
          {exchange.label && <span className="chip tiny">{exchange.label}</span>}
          <span className="chip tiny">
            <Hash size={11} /> audit {compliance.audit_id ?? '–'}
          </span>
          <span className="chip tiny accent">rules v{compliance.rule_version ?? '–'}</span>
          <span className="chip tiny">
            <Timer size={11} /> {compliance.latency_ms} ms
          </span>
          <span className="chip tiny">
            <Cpu size={11} /> {compliance.ai_used ? 'AI used' : 'AI skipped'}
          </span>
        </div>
      </div>

      <p className="outcome">
        {approved
          ? 'Every fact matched the trusted rules, so the customer sees the original answer.'
          : 'The raw answer was blocked. The customer sees a pre-approved safe message instead:'}
      </p>
      {!approved && <blockquote className="safe-message">{customer.text}</blockquote>}
      {compliance.error && (
        <p className="error-note">
          <strong>Check failed:</strong> {compliance.error}
        </p>
      )}

      <h3>Raw AI answer</h3>
      <RawAnswer text={compliance.raw_answer} results={compliance.results} />

      <h3>
        Extracted facts <span className="count">{compliance.results.length}</span>
      </h3>
      <FactList results={compliance.results} />

      <h3>Pipeline trace</h3>
      <TraceView trace={compliance.trace} />

      <h3>AI calls</h3>
      <AICalls calls={compliance.governance.ai_calls} />
    </div>
  )
}
