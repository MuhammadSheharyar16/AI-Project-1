import { motion } from 'framer-motion'
import { Bot, Code2, Gavel, Hand, MessageSquare, ScanSearch, ScrollText, Sparkles, Zap, type LucideIcon } from 'lucide-react'
import { Fragment } from 'react'

const STEPS: { icon: LucideIcon; title: string; detail: string; tone?: string }[] = [
  { icon: Bot, title: 'AI answer', detail: 'Written by the assistant, not checked yet' },
  { icon: Hand, title: 'Intercept', detail: 'Held before the customer sees it' },
  { icon: ScanSearch, title: 'Extract facts', detail: 'Pattern rules + AI: prices, %, dates, links, promises' },
  { icon: Code2, title: 'Code checks', detail: 'Prices, links and banned phrases, in plain code' },
  { icon: Sparkles, title: 'AI policy check', detail: 'Promises vs policy, with a verified quote', tone: 'violet' },
  { icon: Gavel, title: 'Decision', detail: 'Approved, Rejected or Error' },
]

const EFFICIENCY = [
  { title: 'Cheap checks first', text: 'If a code check already fails, the AI check is skipped. Saves time and cost.' },
  { title: 'No facts, no AI', text: 'A greeting with nothing to verify is approved instantly.' },
  { title: 'Rules load once', text: 'They are cached and reload only when the version number changes.' },
]

/** The architecture, as an animated flow. */
export function Pipeline() {
  return (
    <div className="pipeline">
      <div className="pipeline-flow">
        {STEPS.map(({ icon: Icon, title, detail, tone }, i) => (
          <Fragment key={title}>
            <motion.div
              className={`pipe-node ${tone ?? ''}`}
              initial={{ opacity: 0, y: 18 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ delay: i * 0.08 }}
            >
              <span className="pipe-icon">
                <Icon size={18} />
              </span>
              <strong>{title}</strong>
              <small>{detail}</small>
            </motion.div>
            <span className="pipe-link" style={{ animationDelay: `${i * 0.35}s` }} aria-hidden="true" />
          </Fragment>
        ))}
        <div className="pipe-outcomes">
          <div className="pipe-node ok">
            <span className="pipe-icon">
              <MessageSquare size={18} />
            </span>
            <strong>Customer</strong>
            <small>Approved text, or a pre-approved safe message</small>
          </div>
          <div className="pipe-node">
            <span className="pipe-icon">
              <ScrollText size={18} />
            </span>
            <strong>Audit log</strong>
            <small>Every decision, with the rule version used</small>
          </div>
        </div>
      </div>
      <div className="efficiency">
        {EFFICIENCY.map(({ title, text }) => (
          <div key={title}>
            <Zap size={14} />
            <p>
              <strong>{title}.</strong> {text}
            </p>
          </div>
        ))}
      </div>
    </div>
  )
}
