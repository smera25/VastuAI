import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Bath, BedDouble, BookOpen, CookingPot, Sofa, Utensils, Home } from 'lucide-react'
import { BUDGETS, ROOM_TYPES, STYLES } from '../lib/furniture.js'
import { useProject } from '../state/project.jsx'
import { Field, PageHead, Unit } from '../components/ui.jsx'
import { StepFooter } from '../components/Shell.jsx'

const ICON = { bedroom: BedDouble, living_room: Sofa, kitchen: CookingPot, study_room: BookOpen, dining_room: Utensils, other: Home }

export function validateSetup(s) {
  const errors = {}
  if (!s.name.trim()) errors.name = 'Give this room a name, e.g. “Master bedroom”.'
  for (const k of ['width', 'length']) {
    if (s[k] === '' || s[k] == null) continue
    const n = Number(s[k])
    if (!Number.isFinite(n) || n < 2 || n > 15) errors[k] = 'Enter a value between 2 and 15 metres, or leave it blank.'
  }
  if ((s.width === '') !== (s.length === '')) errors.length = 'Enter both width and length, or leave both blank.'
  return errors
}

export default function Setup() {
  const { project, set, invalidate } = useProject()
  const nav = useNavigate()
  const s = project.setup
  const [touched, setTouched] = useState(false)
  const errors = validateSetup(s)
  const update = (patch) => { set('setup', patch); if (project.analysis.status === 'done') invalidate('analysis') }
  const next = () => { setTouched(true); if (Object.keys(errors).length === 0) nav('/project/photos') }
  const show = (k) => (touched || s[k]) && errors[k]

  return (
    <div className="narrow-form stack" style={{ '--gap': '1.75rem' }}>
      <PageHead eyebrow="Step 1 · The room" title="Tell us about the room">A few basics now; you can refine everything later. Measurements are optional — but any you know make the result more trustworthy.</PageHead>

      <div className="card stack">
        <Field label="Room name" htmlFor="name" error={show('name')}>
          <input id="name" className="input" value={s.name} maxLength={60} placeholder="e.g. Master bedroom" aria-invalid={!!show('name')} onChange={(e) => update({ name: e.target.value })} />
        </Field>
        <fieldset className="field" style={{ border: 0, padding: 0, margin: 0 }}>
          <legend className="label" style={{ fontWeight: 600, fontSize: '.88rem', marginBottom: '.5rem' }}>Room type</legend>
          <div className="tiles" role="radiogroup" aria-label="Room type">
            {ROOM_TYPES.map((r) => {
              const Icon = ICON[r.value] ?? Bath
              return (
                <button key={r.value} type="button" role="radio" aria-checked={s.roomType === r.value} className="tile" onClick={() => update({ roomType: r.value })}>
                  <Icon size={22} strokeWidth={1.5} /><span>{r.label}</span>
                </button>
              )
            })}
          </div>
        </fieldset>
      </div>

      <div className="card stack">
        <div><h3>Approximate dimensions <span className="chip dashed">optional</span></h3><p className="small muted" style={{ margin: 0 }}>Floor-area measurements in metres. If you leave these blank, any size we estimate from photos will be labelled as an estimate (often off by 20% or more).</p></div>
        <div className="grid cols-2">
          <Field label="Width (left–right in the plan)" htmlFor="w" error={show('width')}>
            <Unit unit="m"><input id="w" className="input" inputMode="decimal" value={s.width} placeholder="e.g. 4.0" aria-invalid={!!show('width')} onChange={(e) => update({ width: e.target.value })} /></Unit>
          </Field>
          <Field label="Length (top–bottom in the plan)" htmlFor="l" error={show('length')}>
            <Unit unit="m"><input id="l" className="input" inputMode="decimal" value={s.length} placeholder="e.g. 3.5" aria-invalid={!!show('length')} onChange={(e) => update({ length: e.target.value })} /></Unit>
          </Field>
        </div>
      </div>

      <div className="card stack">
        <h3>Preferred interior style</h3>
        <div className="style-grid" role="radiogroup" aria-label="Interior style">
          {STYLES.map((st) => (
            <button key={st.value} type="button" role="radio" aria-checked={s.style === st.value} className="style-card" onClick={() => { update({ style: st.value }); set('prefs', { style: st.value }) }}>
              <span className="swatches">{st.swatch.map((c) => <i key={c} style={{ background: c }} />)}</span>
              <b>{st.label}</b><span className="small muted">{st.blurb}</span>
            </button>
          ))}
        </div>
        <Field label="Budget range" help="Optional. Used only to compare against indicative costs for new or replaced items." htmlFor="budget">
          <select id="budget" className="select" value={s.budgetValue} onChange={(e) => { update({ budgetValue: e.target.value }); set('prefs', { budgetValue: e.target.value }) }}>
            {BUDGETS.map((b) => <option key={b.value} value={b.value}>{b.label}</option>)}
          </select>
        </Field>
      </div>
      <StepFooter next="/project/photos" onNext={next} nextLabel="Continue to photos" hint={touched && Object.keys(errors).length ? 'Please fix the highlighted fields.' : undefined} />
    </div>
  )
}
