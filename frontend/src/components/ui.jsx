import { AlertTriangle, CheckCircle2, Info, XCircle } from 'lucide-react'

export function Button({ variant = '', size = '', icon, children, ...rest }) {
  return (
    <button type="button" className={`btn ${variant} ${size}`.trim()} {...rest}>
      {icon}{children}
    </button>
  )
}

export function Field({ label, help, error, children, htmlFor }) {
  return (
    <div className="field">
      {label && <label htmlFor={htmlFor}>{label}</label>}
      {children}
      {help && !error && <span className="help">{help}</span>}
      {error && <span className="err" role="alert">{error}</span>}
    </div>
  )
}

export function Unit({ unit, children }) {
  return <div className="input-unit">{children}<span aria-hidden="true">{unit}</span></div>
}

export function Segmented({ value, options, onChange, label }) {
  return (
    <div className="seg" role="group" aria-label={label}>
      {options.map((o) => (
        <button key={o.value} type="button" aria-pressed={value === o.value} onClick={() => onChange(o.value)}>{o.label}</button>
      ))}
    </div>
  )
}

const ICONS = { info: Info, warn: AlertTriangle, danger: XCircle, ok: CheckCircle2 }
export function Alert({ kind = 'info', title, children, action }) {
  const Icon = ICONS[kind]
  return (
    <div className={`alert ${kind}`} role={kind === 'danger' ? 'alert' : 'status'}>
      <Icon size={18} aria-hidden="true" />
      <div className="body">
        {title && <strong>{title}</strong>}
        {children && <p>{children}</p>}
      </div>
      {action}
    </div>
  )
}

export const Spinner = ({ label = 'Loading' }) => <span className="spinner" role="status" aria-label={label} />

export function Chip({ kind = '', children, title }) {
  return <span className={`chip ${kind}`} title={title}>{children}</span>
}

/** Provenance chip - makes clear WHERE a value came from. */
const PROV = {
  detected: ['info', 'Auto-detected'], user_confirmed: ['sage', 'You confirmed'], user_provided: ['sage', 'You provided'],
  user_added: ['sage', 'You added'], estimated: ['warn', 'Estimated'], default: ['dashed', 'Typical size (estimate)'],
  reconstructed: ['warn', 'Estimated from photos'], user: ['sage', 'You provided'],
}
export function Provenance({ kind }) {
  const [cls, label] = PROV[kind] ?? ['', kind]
  return <Chip kind={cls}>{label}</Chip>
}

export function PageHead({ eyebrow, title, children }) {
  return (
    <header className="page-head fade-in">
      {eyebrow && <div className="eyebrow">{eyebrow}</div>}
      <h2>{title}</h2>
      {children && <p>{children}</p>}
    </header>
  )
}
