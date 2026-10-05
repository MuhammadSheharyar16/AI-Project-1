import type {
  AuditEntry,
  AuditPage,
  ChatMode,
  CheckResponse,
  DecisionStatus,
  GovernanceReport,
  Health,
  Review,
  Rules,
  RulesResponse,
  RuleVersionInfo,
  Simulate,
  Source,
  SuiteInfo,
  SuiteReport,
} from './types'

// Same-origin: the Vite server proxies /api to the backend and adds the auth headers.
const BASE = '/api'

export class ApiError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

interface ValidationIssue {
  loc?: (string | number)[]
  msg?: string
}

/** FastAPI sends `detail` as a string, or as a list of issues for 422. */
function describe(detail: unknown, status: number): string {
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    return (detail as ValidationIssue[])
      .map((issue) => {
        const where = (issue.loc ?? []).filter((part) => part !== 'body' && part !== 'rules').join(' › ')
        return where ? `${where}: ${issue.msg}` : String(issue.msg)
      })
      .join('\n')
  }
  return `Request failed (HTTP ${status})`
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(BASE + path, {
      ...init,
      headers: init?.body ? { 'Content-Type': 'application/json' } : undefined,
    })
  } catch {
    throw new ApiError(0, 'Cannot reach the backend. Is it running on port 8000?')
  }
  if (!response.ok) {
    const body = await response.json().catch(() => null)
    // The Vite proxy answers 5xx with no JSON body when the backend is down.
    if (body === null && response.status >= 500) {
      throw new ApiError(response.status, 'Cannot reach the backend. Is it running on port 8000?')
    }
    throw new ApiError(response.status, describe(body?.detail, response.status))
  }
  return response.json() as Promise<T>
}

const post = (body?: unknown): RequestInit => ({
  method: 'POST',
  body: body === undefined ? undefined : JSON.stringify(body),
})

export interface AuditFilters {
  decision?: DecisionStatus
  version?: number
  source?: Source
  q?: string
  limit: number
  offset: number
}

export const api = {
  health: () => request<Health>('/health'),

  chat: (question: string, mode: ChatMode) => request<CheckResponse>('/chat', post({ question, mode })),

  check: (answer: string, question = '', simulate?: Simulate) =>
    request<CheckResponse>(`/check${simulate ? `?simulate=${simulate}` : ''}`, post({ question, answer })),

  rules: () => request<RulesResponse>('/rules'),

  ruleVersions: () => request<RuleVersionInfo[]>('/rules/versions'),

  saveRules: (rules: Rules, author: string, note: string) =>
    request<RulesResponse>('/rules', {
      method: 'PUT',
      body: JSON.stringify({ rules, author, note: note || null }),
    }),

  restoreRules: (version: number, author: string) =>
    request<RulesResponse>(`/rules/restore/${version}`, post({ author })),

  audit: (filters: AuditFilters) => {
    const params = new URLSearchParams()
    for (const [key, value] of Object.entries(filters)) {
      if (value !== undefined && value !== '') params.set(key, String(value))
    }
    return request<AuditPage>(`/audit?${params}`)
  },

  auditEntry: (id: number) => request<AuditEntry>(`/audit/${id}`),

  recheck: (id: number) => request<CheckResponse>(`/audit/${id}/recheck`, post()),

  review: (id: number, reviewer: string, verdict: Review['verdict'], note: string) =>
    request<Review>(`/audit/${id}/review`, post({ reviewer, verdict, note: note || null })),

  governance: () => request<GovernanceReport>('/governance'),

  suiteInfo: () => request<SuiteInfo>('/suite'),

  runSuite: () => request<SuiteReport>('/suite/run', post()),
}
