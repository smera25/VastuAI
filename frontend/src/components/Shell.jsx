import { Link, NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { Check, RotateCcw } from 'lucide-react'
import { useProject } from '../state/project.jsx'
import { STEPS, furthestStep } from '../lib/steps.js'
import { Button } from './ui.jsx'
import { useState } from 'react'

export function Header({ showReset = true }) {
  const { reset } = useProject()
  const nav = useNavigate()
  const [confirming, setConfirming] = useState(false)
  return (
    <header className="site-header">
      <div className="inner">
        <Link to="/" className="brand" aria-label="Vastu Atelier home">
          <span className="brand-mark" aria-hidden="true">
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6"><rect x="2" y="2" width="12" height="12" rx="1" /><path d="M8 5v6M5 8h6" strokeLinecap="round" /></svg>
          </span>
          Vastu Atelier
        </Link>
        {showReset && <div className="row">
          {confirming ? (
            <>
              <span className="small muted">Discard this room and start over?</span>
              <Button size="sm" variant="danger-ghost" onClick={async () => { await reset(); setConfirming(false); nav('/') }}>Yes, discard</Button>
              <Button size="sm" variant="ghost" onClick={() => setConfirming(false)}>Keep</Button>
            </>
          ) : (
            <Button size="sm" variant="ghost" icon={<RotateCcw size={15} />} onClick={() => setConfirming(true)}>Start over</Button>
          )}
        </div>}
      </div>
    </header>
  )
}

export function Stepper() {
  const { project } = useProject()
  const { pathname } = useLocation()
  const idx = STEPS.findIndex((s) => pathname.startsWith(s.path))
  const reach = furthestStep(project)
  return (
    <nav className="stepper" aria-label="Progress">
      <ol>
        {STEPS.map((s, i) => {
          const state = i === idx ? 'current' : i < idx || i < reach ? 'done' : ''
          return (
            <li key={s.path}>
              <NavLink to={s.path} className={`step-pill ${state}`} aria-current={i === idx ? 'step' : undefined} aria-disabled={i > reach}>
                <span className="n">{state === 'done' ? <Check size={13} /> : i + 1}</span>
                <span className="label">{s.label}</span>
              </NavLink>
            </li>
          )
        })}
      </ol>
      <div className="bar" aria-hidden="true"><i style={{ width: `${((idx + 1) / STEPS.length) * 100}%` }} /></div>
    </nav>
  )
}

export function WizardLayout() {
  return (
    <>
      <Header />
      <Stepper />
      <main className="page"><Outlet /></main>
    </>
  )
}

/** Sticky bottom navigation shared by every wizard page. */
export function StepFooter({ back, next, nextLabel = 'Continue', nextDisabled, onNext, hint, busy, nextIcon }) {
  const nav = useNavigate()
  return (
    <div className="step-footer">
      <div className="inner">
        {back ? <Button variant="ghost" onClick={() => nav(back)}>Back</Button> : <span />}
        <span className="hint" aria-live="polite">{hint}</span>
        <Button variant="sage" disabled={nextDisabled || busy} onClick={() => (onNext ? onNext() : nav(next))} icon={nextIcon}>{nextLabel}</Button>
      </div>
    </div>
  )
}
