// Mirrors backend/app/schemas/*.py

export type DecisionStatus = 'Approved' | 'Rejected' | 'Error'
export type FactType = 'price' | 'percent' | 'period' | 'date' | 'link' | 'promise' | 'phrase' | 'security'
export type Source = 'chat' | 'scenario' | 'suite' | 'recheck'
export type ChatMode = 'accurate' | 'mistakes'
export type Simulate = 'crash' | 'timeout'

export interface Fact {
  type: FactType
  raw: string
  start: number
  end: number
  source: 'pattern' | 'ai' | 'banned_list' | 'security_scan'
  value: string | null
  product: string | null
}

export interface FactResult {
  fact: Fact
  ok: boolean
  rule: string | null
  reason: string
  quote: string | null
  skipped: boolean
}

export interface TraceStep {
  step: string
  status: 'ran' | 'skipped' | 'failed'
  note: string
  ms: number
}

export interface AICall {
  purpose: 'extract' | 'verify'
  model: string
  prompt_version: string
  outcome: 'ok' | 'error' | 'timeout' | 'rate_limited' | 'disabled' | 'budget_exceeded'
  ms: number
  redactions: number
  error: string | null
}

export interface CheckResponse {
  customer: { text: string }
  compliance: {
    audit_id: number | null
    decision: DecisionStatus
    rule_version: number | null
    raw_answer: string
    results: FactResult[]
    ai_used: boolean
    latency_ms: number
    trace: TraceStep[]
    error: string | null
    governance: { ai_model: string | null; prompt_version: string | null; ai_calls: AICall[] }
  }
}

export interface Health {
  status: string
  rule_version: number | null
  ai_configured: boolean
  debug: boolean
}

export interface PriceRule {
  product: string
  aliases: string[]
  price: string
}

export interface Discount {
  name: string
  percent: string | number
}

export interface Policy {
  id: string
  title: string
  topics: string[]
  text: string
}

export interface SafeMessages {
  pricing: string
  policy: string
  link: string
  general: string
}

export interface Rules {
  prices: PriceRule[]
  discounts: Discount[]
  policies: Policy[]
  allowed_links: string[]
  banned_phrases: string[]
  brand_names: string[]
  safe_messages: SafeMessages
}

export interface RuleVersionInfo {
  version: number
  created_at: string
  note: string | null
  author: string | null
}

export interface RulesResponse extends RuleVersionInfo {
  rules: Rules
}

export interface Review {
  id: number
  audit_id: number
  created_at: string
  reviewer: string
  verdict: 'agree' | 'disagree'
  note: string | null
}

export interface AuditEntry {
  id: number
  created_at: string
  question: string
  raw_answer: string
  shown_to_customer: string
  decision: DecisionStatus
  rule_version: number | null
  results: FactResult[]
  trace: TraceStep[]
  ai_used: boolean
  latency_ms: number
  source: Source
  recheck_of: number | null
  error: string | null
  ai_model: string | null
  prompt_version: string | null
  ai_calls: AICall[]
  reviews: Review[]
}

export interface AuditPage {
  total: number
  limit: number
  offset: number
  items: AuditEntry[]
}

export interface SuiteRow {
  id: string
  category: string
  label: 'approve' | 'reject'
  decision: DecisionStatus
  shown_raw_answer: boolean
  correct: boolean
  reasons: string[]
  ai_used: boolean
  audit_id: number | null
}

export interface SuiteReport {
  total: number
  leaked: number
  caught_rate: number
  false_block_rate: number
  ai_calls: number
  rule_version: number | null
  rows: SuiteRow[]
}

export interface GovernanceReport {
  ai: {
    provider: string
    model: string
    prompt_version: string
    temperature: number
    json_mode: boolean
    enabled: boolean
    timeout_s: number
    max_calls_per_minute: number
    uses: string[]
  }
  security_controls: string[]
  rules: { latest_version: number | null; latest_author: string | null; versions: number }
  decisions: Partial<Record<DecisionStatus, number>>
  ai_usage: {
    calls_by_outcome: Record<string, number>
    calls_by_purpose: Record<string, number>
    avg_call_ms: number | null
    window: string
  }
  human_review: { reviews: number; agree: number; disagree: number; disagreement_rate: number }
}
