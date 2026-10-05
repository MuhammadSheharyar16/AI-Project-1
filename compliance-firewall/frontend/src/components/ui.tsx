import { motion, useMotionTemplate, useMotionValue, useSpring } from 'framer-motion'
import { AlertTriangle, Check, Loader2, ShieldCheck, ShieldX, X } from 'lucide-react'
import { useState, type KeyboardEvent, type PointerEvent, type ReactNode } from 'react'
import type { DecisionStatus } from '../api/types'

export const DECISION_CLASS: Record<DecisionStatus, string> = {
  Approved: 'ok',
  Rejected: 'bad',
  Error: 'warn',
}

const DECISION_ICON = { Approved: ShieldCheck, Rejected: ShieldX, Error: AlertTriangle }

export function DecisionBadge({ decision, large }: { decision: DecisionStatus; large?: boolean }) {
  const Icon = DECISION_ICON[decision]
  return (
    <span className={`badge ${DECISION_CLASS[decision]}${large ? ' large' : ''}`}>
      <Icon size={large ? 18 : 13} />
      {decision}
    </span>
  )
}

interface PanelProps {
  title?: ReactNode
  icon?: ReactNode
  actions?: ReactNode
  className?: string
  children: ReactNode
}

/** Glass panel with sharp corner brackets. */
export function Panel({ title, icon, actions, className = '', children }: PanelProps) {
  return (
    <section className={`panel ${className}`}>
      {(title || actions) && (
        <header className="panel-head">
          <h2>
            {icon}
            {title}
          </h2>
          {actions && <div className="panel-actions">{actions}</div>}
        </header>
      )}
      {children}
    </section>
  )
}

/** Card that tilts in 3D toward the pointer, with a glare that follows it. */
export function TiltCard({ className = '', children }: { className?: string; children: ReactNode }) {
  const rotateX = useSpring(useMotionValue(0), { stiffness: 220, damping: 18 })
  const rotateY = useSpring(useMotionValue(0), { stiffness: 220, damping: 18 })
  const glareX = useMotionValue(50)
  const glareY = useMotionValue(50)
  const glare = useMotionTemplate`radial-gradient(260px circle at ${glareX}% ${glareY}%, rgba(56, 225, 255, 0.16), transparent 70%)`

  const onMove = (event: PointerEvent<HTMLDivElement>) => {
    if (event.pointerType === 'touch') return
    const box = event.currentTarget.getBoundingClientRect()
    const x = (event.clientX - box.left) / box.width
    const y = (event.clientY - box.top) / box.height
    rotateY.set((x - 0.5) * 14)
    rotateX.set((0.5 - y) * 14)
    glareX.set(x * 100)
    glareY.set(y * 100)
  }
  const onLeave = () => {
    rotateX.set(0)
    rotateY.set(0)
  }

  return (
    <div className="tilt-wrap">
      <motion.div
        className={`tilt ${className}`}
        style={{ rotateX, rotateY }}
        onPointerMove={onMove}
        onPointerLeave={onLeave}
      >
        <motion.div className="tilt-glare" style={{ background: glare }} />
        {children}
      </motion.div>
    </div>
  )
}

export function Spinner({ size = 16 }: { size?: number }) {
  return <Loader2 size={size} className="spin" />
}

interface SegmentedProps<T extends string> {
  value: T
  options: { value: T; label: ReactNode; tone?: string }[]
  onChange: (value: T) => void
  label: string
}

export function Segmented<T extends string>({ value, options, onChange, label }: SegmentedProps<T>) {
  return (
    <div className="segmented" role="radiogroup" aria-label={label}>
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          role="radio"
          aria-checked={option.value === value}
          className={`${option.value === value ? 'active' : ''} ${option.tone ?? ''}`}
          onClick={() => onChange(option.value)}
        >
          {option.label}
        </button>
      ))}
    </div>
  )
}

interface TagInputProps {
  values: string[]
  onChange: (values: string[]) => void
  placeholder: string
  tone?: 'bad' | 'ok' | ''
}

/** Chips with an input: Enter or comma adds, × or Backspace removes. */
export function TagInput({ values, onChange, placeholder, tone = '' }: TagInputProps) {
  const [draft, setDraft] = useState('')

  const commit = () => {
    const value = draft.trim()
    if (value && !values.some((v) => v.toLowerCase() === value.toLowerCase())) onChange([...values, value])
    setDraft('')
  }
  const onKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'Enter' || event.key === ',') {
      event.preventDefault()
      commit()
    } else if (event.key === 'Backspace' && !draft && values.length) {
      onChange(values.slice(0, -1))
    }
  }

  return (
    <div className="tag-input">
      {values.map((value, i) => (
        <span key={value} className={`tag ${tone}`}>
          {value}
          <button type="button" aria-label={`Remove ${value}`} onClick={() => onChange(values.filter((_, j) => j !== i))}>
            <X size={12} />
          </button>
        </span>
      ))}
      <input
        value={draft}
        placeholder={placeholder}
        onChange={(event) => setDraft(event.target.value)}
        onKeyDown={onKeyDown}
        onBlur={commit}
      />
    </div>
  )
}

export function Mark({ ok }: { ok: boolean }) {
  return <span className={`mark ${ok ? 'ok' : 'bad'}`}>{ok ? <Check size={14} /> : <X size={14} />}</span>
}

export function EmptyState({ icon, title, children }: { icon: ReactNode; title: string; children?: ReactNode }) {
  return (
    <div className="empty">
      <div className="empty-icon">{icon}</div>
      <strong>{title}</strong>
      {children && <p>{children}</p>}
    </div>
  )
}

export function ErrorNote({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="error-note" role="alert">
      <AlertTriangle size={16} />
      <span>{message}</span>
      {onRetry && (
        <button type="button" className="btn ghost small" onClick={onRetry}>
          Retry
        </button>
      )}
    </div>
  )
}

export function formatTime(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}
