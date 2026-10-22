import { CheckCircle2, Circle, MinusCircle, XCircle } from 'lucide-react'
import { Spinner } from './ui.jsx'

const ICON = {
  done: <CheckCircle2 size={18} color="var(--ok)" />, failed: <XCircle size={18} color="var(--danger)" />,
  skipped: <MinusCircle size={18} color="var(--muted)" />, pending: <Circle size={18} color="var(--line-strong)" />,
}

/** Renders the REAL stage list reported by the backend job - nothing here is simulated. */
export default function JobProgress({ stages, title }) {
  return (
    <ol className="job-stages" aria-label={title ?? 'Progress'} aria-live="polite">
      {stages.map((s) => (
        <li key={s.key} className={`job-stage ${s.status}`}>
          <span className="icon">{s.status === 'running' ? <Spinner label={s.label} /> : ICON[s.status]}</span>
          <div>
            <div className="job-label">{s.label}{s.status === 'skipped' && <span className="muted"> — skipped</span>}{s.status === 'failed' && <span style={{ color: 'var(--danger)' }}> — failed</span>}</div>
            {s.detail && <div className="small muted">{s.detail}</div>}
          </div>
        </li>
      ))}
    </ol>
  )
}
