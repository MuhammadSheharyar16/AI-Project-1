import { AnimatePresence, motion } from 'framer-motion'
import {
  BadgeDollarSign,
  Ban,
  FileText,
  History,
  Link2,
  MessageSquareWarning,
  Percent,
  Plus,
  RotateCcw,
  Save,
  Tag,
  Trash2,
  Undo2,
} from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { api, ApiError } from '../api/client'
import type { Rules, RulesResponse, RuleVersionInfo, SafeMessages } from '../api/types'
import { ErrorNote, formatTime, Panel, Spinner, TagInput } from '../components/ui'
import { useStore } from '../store'

const AUTHOR_KEY = 'firewall.author'

const SAFE_MESSAGE_FIELDS: { key: keyof SafeMessages; label: string; hint: string }[] = [
  { key: 'pricing', label: 'Pricing', hint: 'Shown when a price or discount is wrong' },
  { key: 'policy', label: 'Policy', hint: 'Shown for wrong promises, periods, dates or banned phrases' },
  { key: 'link', label: 'Link', hint: 'Shown when a link is not on the allowed list' },
  { key: 'general', label: 'General', hint: 'Shown when the check itself fails (Error) or on a security hit' },
]

const splitList = (text: string) =>
  text
    .split(',')
    .map((part) => part.trim())
    .filter(Boolean)

/** Text input for a comma-separated list: keeps the raw text while typing, commits on blur. */
function ListField({ values, onChange, placeholder, label }: {
  values: string[]
  onChange: (values: string[]) => void
  placeholder: string
  label: string
}) {
  const [text, setText] = useState<string | null>(null)
  return (
    <input
      aria-label={label}
      placeholder={placeholder}
      value={text ?? values.join(', ')}
      onChange={(event) => {
        setText(event.target.value)
        onChange(splitList(event.target.value))
      }}
      onBlur={() => setText(null)}
    />
  )
}

export function RulesPage() {
  const { toast, refreshHealth } = useStore()
  const [saved, setSaved] = useState<RulesResponse | null>(null)
  const [draft, setDraft] = useState<Rules | null>(null)
  const [versions, setVersions] = useState<RuleVersionInfo[]>([])
  const [author, setAuthor] = useState(() => localStorage.getItem(AUTHOR_KEY) ?? '')
  const [note, setNote] = useState('')
  const [loadError, setLoadError] = useState<string | null>(null)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  const accept = useCallback((response: RulesResponse) => {
    setSaved(response)
    setDraft(structuredClone(response.rules))
    setSaveError(null)
    setNote('')
  }, [])

  const load = useCallback(async () => {
    setLoadError(null)
    try {
      const [rules, list] = await Promise.all([api.rules(), api.ruleVersions()])
      accept(rules)
      setVersions(list)
    } catch (error) {
      setLoadError(error instanceof ApiError ? error.message : 'Could not load the rules')
    }
  }, [accept])

  useEffect(() => {
    void load()
  }, [load])

  if (loadError) return <ErrorNote message={loadError} onRetry={load} />
  if (!saved || !draft) {
    return (
      <div className="loading">
        <Spinner size={22} /> Loading trusted rules…
      </div>
    )
  }

  const dirty = JSON.stringify(draft) !== JSON.stringify(saved.rules)
  const set = <K extends keyof Rules>(key: K, value: Rules[K]) => setDraft({ ...draft, [key]: value })
  const setAt = <K extends 'prices' | 'discounts' | 'policies'>(key: K, index: number, change: Partial<Rules[K][number]>) =>
    set(key, draft[key].map((item, i) => (i === index ? { ...item, ...change } : item)) as Rules[K])
  const removeAt = <K extends 'prices' | 'discounts' | 'policies' | 'allowed_links'>(key: K, index: number) =>
    set(key, draft[key].filter((_, i) => i !== index) as Rules[K])

  const rememberAuthor = () => {
    const name = author.trim()
    if (!name) {
      setSaveError('Enter your name: every rules version records who made it.')
      return null
    }
    localStorage.setItem(AUTHOR_KEY, name)
    return name
  }

  const afterWrite = async (response: RulesResponse, message: string) => {
    accept(response)
    setVersions(await api.ruleVersions())
    void refreshHealth()
    toast('ok', message)
  }

  const save = async () => {
    const name = rememberAuthor()
    if (!name) return
    setSaving(true)
    setSaveError(null)
    try {
      const response = await api.saveRules(draft, name, note.trim())
      await afterWrite(response, `Saved as rules v${response.version}. New checks use it immediately.`)
    } catch (error) {
      setSaveError(error instanceof ApiError ? error.message : 'Save failed')
    } finally {
      setSaving(false)
    }
  }

  const restore = async (version: number) => {
    const name = rememberAuthor()
    if (!name) return
    if (dirty && !window.confirm('Restoring will discard your unsaved edits. Continue?')) return
    setSaving(true)
    try {
      const response = await api.restoreRules(version, name)
      await afterWrite(response, `Restored v${version} as the new v${response.version}.`)
    } catch (error) {
      setSaveError(error instanceof ApiError ? error.message : 'Restore failed')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="stack">
      <div className="page-head">
        <div>
          <h1>
            Trusted rules <span className="version-badge">v{saved.version}</span>
          </h1>
          <p>
            The source of truth every AI answer is checked against. Saving never overwrites: it creates version{' '}
            {saved.version + 1}.
          </p>
        </div>
        <div className="muted small right">
          Last saved {formatTime(saved.created_at)}
          <br />
          by {saved.author ?? 'unknown'}
          {saved.note ? ` · “${saved.note}”` : ''}
        </div>
      </div>

      <div className="rules-layout">
        <div className="stack">
          <Panel
            title="Official prices"
            icon={<BadgeDollarSign size={16} />}
            actions={
              <button
                type="button"
                className="btn ghost small"
                onClick={() => set('prices', [...draft.prices, { product: '', aliases: [], price: '', other_prices: [] }])}
              >
                <Plus size={14} /> Add plan
              </button>
            }
          >
            <div className="form-table prices">
              <div className="form-head">
                <span>Product</span>
                <span>Also called</span>
                <span>Official price</span>
                <span>Other currencies</span>
                <span />
              </div>
              {draft.prices.map((price, i) => (
                <div key={i} className="form-row">
                  <input
                    aria-label="Product"
                    value={price.product}
                    placeholder="Pro plan"
                    onChange={(event) => setAt('prices', i, { product: event.target.value })}
                  />
                  <ListField
                    label="Aliases"
                    values={price.aliases}
                    placeholder="pro"
                    onChange={(aliases) => setAt('prices', i, { aliases })}
                  />
                  <input
                    aria-label="Official price"
                    className="mono strong"
                    value={price.price}
                    placeholder="USD 49"
                    onChange={(event) => setAt('prices', i, { price: event.target.value })}
                  />
                  <ListField
                    label="Other currency prices"
                    values={price.other_prices}
                    placeholder="Rs 13,999"
                    onChange={(other_prices) => setAt('prices', i, { other_prices })}
                  />
                  <button type="button" className="icon-btn" aria-label={`Remove ${price.product}`} onClick={() => removeAt('prices', i)}>
                    <Trash2 size={15} />
                  </button>
                </div>
              ))}
            </div>
            <p className="muted small">Formats like “USD 49”, “$49” and “Rs 4,999” all work. Prices are never converted between currencies.</p>
          </Panel>

          <Panel
            title="Approved discounts"
            icon={<Percent size={16} />}
            actions={
              <button
                type="button"
                className="btn ghost small"
                onClick={() => set('discounts', [...draft.discounts, { name: '', percent: '' }])}
              >
                <Plus size={14} /> Add discount
              </button>
            }
          >
            <div className="form-table discounts">
              {draft.discounts.length === 0 && <p className="muted small">No discounts: any percentage in an answer is rejected.</p>}
              {draft.discounts.map((discount, i) => (
                <div key={i} className="form-row">
                  <input
                    aria-label="Discount name"
                    value={discount.name}
                    placeholder="Annual billing"
                    onChange={(event) => setAt('discounts', i, { name: event.target.value })}
                  />
                  <div className="suffix-input">
                    <input
                      aria-label="Percent"
                      className="mono strong"
                      type="number"
                      min={0}
                      max={100}
                      step="any"
                      value={discount.percent}
                      onChange={(event) => setAt('discounts', i, { percent: event.target.value })}
                    />
                    <span>%</span>
                  </div>
                  <button type="button" className="icon-btn" aria-label={`Remove ${discount.name}`} onClick={() => removeAt('discounts', i)}>
                    <Trash2 size={15} />
                  </button>
                </div>
              ))}
            </div>
          </Panel>

          <Panel
            title="Policies"
            icon={<FileText size={16} />}
            actions={
              <button
                type="button"
                className="btn ghost small"
                onClick={() => set('policies', [...draft.policies, { id: '', title: '', topics: [], text: '' }])}
              >
                <Plus size={14} /> Add policy
              </button>
            }
          >
            <div className="policy-list">
              {draft.policies.map((policy, i) => (
                <div key={i} className="policy-card">
                  <div className="policy-top">
                    <label>
                      <span>Title</span>
                      <input value={policy.title} placeholder="Refund policy" onChange={(event) => setAt('policies', i, { title: event.target.value })} />
                    </label>
                    <label>
                      <span>ID</span>
                      <input
                        className="mono"
                        value={policy.id}
                        placeholder="refund"
                        onChange={(event) => setAt('policies', i, { id: event.target.value })}
                      />
                    </label>
                    <label>
                      <span>Topic words</span>
                      <ListField
                        label="Topic words"
                        values={policy.topics}
                        placeholder="refund, money back"
                        onChange={(topics) => setAt('policies', i, { topics })}
                      />
                    </label>
                    <button type="button" className="icon-btn" aria-label={`Remove ${policy.title}`} onClick={() => removeAt('policies', i)}>
                      <Trash2 size={15} />
                    </button>
                  </div>
                  <label>
                    <span>Official wording</span>
                    <textarea rows={2} value={policy.text} onChange={(event) => setAt('policies', i, { text: event.target.value })} />
                  </label>
                </div>
              ))}
            </div>
          </Panel>

          <Panel
            title="Allowed links"
            icon={<Link2 size={16} />}
            actions={
              <button type="button" className="btn ghost small" onClick={() => set('allowed_links', [...draft.allowed_links, 'https://'])}>
                <Plus size={14} /> Add link
              </button>
            }
          >
            <div className="form-table links">
              {draft.allowed_links.map((link, i) => (
                <div key={i} className="form-row">
                  <input
                    aria-label="Allowed link"
                    className="mono"
                    value={link}
                    onChange={(event) => set('allowed_links', draft.allowed_links.map((value, j) => (j === i ? event.target.value : value)))}
                  />
                  <button type="button" className="icon-btn" aria-label="Remove link" onClick={() => removeAt('allowed_links', i)}>
                    <Trash2 size={15} />
                  </button>
                </div>
              ))}
            </div>
            <p className="muted small">Capitalisation and a trailing slash are ignored when matching.</p>
          </Panel>

          <div className="two-col">
            <Panel title="Banned phrases" icon={<Ban size={16} />}>
              <TagInput
                tone="bad"
                values={draft.banned_phrases}
                onChange={(values) => set('banned_phrases', values)}
                placeholder="Type a phrase, press Enter"
              />
            </Panel>
            <Panel title="Brand names" icon={<Tag size={16} />}>
              <TagInput values={draft.brand_names} onChange={(values) => set('brand_names', values)} placeholder="Type a name, press Enter" />
              <p className="muted small">Never read as a product, so “Hisaab Pro” is not the “Pro” plan.</p>
            </Panel>
          </div>

          <Panel title="Pre-approved safe messages" icon={<MessageSquareWarning size={16} />}>
            <div className="safe-grid">
              {SAFE_MESSAGE_FIELDS.map(({ key, label, hint }) => (
                <label key={key}>
                  <span>
                    {label} <em>{hint}</em>
                  </span>
                  <textarea
                    rows={3}
                    value={draft.safe_messages[key]}
                    onChange={(event) => set('safe_messages', { ...draft.safe_messages, [key]: event.target.value })}
                  />
                </label>
              ))}
            </div>
          </Panel>
        </div>

        <aside className="stack rules-side">
          <Panel title="Save" icon={<Save size={16} />} className={`save-panel ${dirty ? 'dirty' : ''}`}>
            <p className={`save-state ${dirty ? 'warn-text' : 'muted'}`}>
              {dirty ? `Unsaved changes → will become v${saved.version + 1}` : `No changes since v${saved.version}`}
            </p>
            <label>
              <span>Your name</span>
              <input value={author} maxLength={100} placeholder="Sara (compliance)" onChange={(event) => setAuthor(event.target.value)} />
            </label>
            <label>
              <span>Change note (optional)</span>
              <input value={note} maxLength={500} placeholder="Pro price rise" onChange={(event) => setNote(event.target.value)} />
            </label>
            <AnimatePresence>
              {saveError && (
                <motion.pre className="save-error" initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} exit={{ opacity: 0, height: 0 }}>
                  {saveError}
                </motion.pre>
              )}
            </AnimatePresence>
            <div className="save-actions">
              <button type="button" className="btn primary" disabled={!dirty || saving} onClick={save}>
                {saving ? <Spinner /> : <Save size={15} />} Save as v{saved.version + 1}
              </button>
              <button
                type="button"
                className="btn ghost"
                disabled={!dirty || saving}
                onClick={() => {
                  setDraft(structuredClone(saved.rules))
                  setSaveError(null)
                }}
              >
                <Undo2 size={15} /> Discard
              </button>
            </div>
          </Panel>

          <Panel title="Version history" icon={<History size={16} />}>
            <ol className="versions">
              {versions.map((version) => (
                <li key={version.version} className={version.version === saved.version ? 'current' : ''}>
                  <span className="version-badge small">v{version.version}</span>
                  <div>
                    <strong>{version.note || 'No note'}</strong>
                    <span className="muted small">
                      {version.author ?? 'unknown'} · {formatTime(version.created_at)}
                    </span>
                  </div>
                  {version.version === saved.version ? (
                    <span className="chip tiny ok">live</span>
                  ) : (
                    <button
                      type="button"
                      className="btn ghost small"
                      disabled={saving}
                      title={`Copy v${version.version} into a new version`}
                      onClick={() => restore(version.version)}
                    >
                      <RotateCcw size={13} /> Restore
                    </button>
                  )}
                </li>
              ))}
            </ol>
          </Panel>
        </aside>
      </div>
    </div>
  )
}
