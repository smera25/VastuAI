import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Sparkles } from 'lucide-react'
import FloorPlan, { PlanLegend } from '../components/FloorPlan.jsx'
import JobProgress from '../components/JobProgress.jsx'
import { Alert, Button, Field, PageHead, Provenance } from '../components/ui.jsx'
import { StepFooter } from '../components/Shell.jsx'
import { planRedesign, pollJob, startVisualization } from '../lib/api.js'
import { ACCESS_OPTIONS, BUDGETS, CATALOG, FUNCTION_OPTIONS, PALETTES, STYLES, furnitureTypes } from '../lib/furniture.js'
import { buildLayout, renderableFromLayout } from '../lib/layout.js'
import { EDGES } from '../lib/orientation.js'
import { edgeCaption } from '../lib/layout.js'
import { loadPhotoBlobs, useProject, usePhotoUrls } from '../state/project.jsx'

/** Preferences payload for POST /redesign/plan. */
export function buildPreferences(project) {
  const p = project.prefs
  const palette = PALETTES.find((x) => x.id === p.paletteId)
  const budget = BUDGETS.find((b) => b.value === p.budgetValue)
  return {
    style: p.style, color_palette: palette?.colors ?? [], budget_inr: budget?.inr ?? undefined, budget_label: budget?.label,
    retain: p.retain, replace: p.replace, add: p.add, storage_preference: p.storage,
    functional_requirements: p.functional, accessibility: p.accessibility, wheelchair_clearance: p.wheelchair,
    notes: p.notes, follow_vastu: p.followVastu, reference_view_edge: p.referenceViewEdge,
  }
}

const toggle = (arr, v) => (arr.includes(v) ? arr.filter((x) => x !== v) : [...arr, v])

export default function Redesign() {
  const { project, set, invalidate } = useProject()
  const nav = useNavigate()
  const ctrl = useRef(null)
  const urls = usePhotoUrls(project.photos)
  const [addPick, setAddPick] = useState('desk')
  const { prefs, redesign, visualization, furniture, photos } = project
  const placed = furniture.filter((f) => f.confirmed && Number.isFinite(f.x))
  const busy = redesign.status === 'running' || visualization.status === 'running'
  const p = (patch) => { set('prefs', patch); if (redesign.status !== 'idle') invalidate('redesign') }
  const refPhoto = photos.find((x) => x.id === (prefs.referencePhotoId ?? photos[0]?.id))
  const refIsFirst = !refPhoto || refPhoto.id === photos[0]?.id
  useEffect(() => () => ctrl.current?.abort(), [])

  const generate = async () => {
    ctrl.current?.abort(); ctrl.current = new AbortController()
    const { signal } = ctrl.current
    invalidate('redesign')
    set('redesign', { status: 'running', spec: null, error: null })
    try {
      const spec = await planRedesign(buildLayout(project), { ...buildPreferences(project), reference_view_edge: refIsFirst ? 'top' : prefs.referenceViewEdge }, signal)
      set('redesign', { status: 'done', spec, error: null })
      set('visualization', { status: 'running', jobId: null, stages: [{ key: 'start', label: 'Starting image generation', status: 'running' }], result: null, error: null })
      let blob = null
      if (refPhoto) { const files = await loadPhotoBlobs([refPhoto]); blob = files[0] }
      try {
        const started = await startVisualization(spec.id, blob, signal)
        set('visualization', { jobId: started.job_id })
        const job = await pollJob(started.job_id, { signal, intervalMs: 2000, onUpdate: (j) => set('visualization', { stages: j.stages }) })
        if (job.status === 'failed') set('visualization', { status: 'error', stages: job.stages, error: { message: job.error.message, code: job.error.code, hint: job.error.hint } })
        else set('visualization', { status: 'done', stages: job.stages, result: job.result, error: null })
      } catch (e) {
        if (signal.aborted) return
        // e.g. 503 image_provider_not_configured: surfaced verbatim, never replaced by a placeholder.
        set('visualization', { status: 'error', stages: [], error: { message: e.message, code: e.code, hint: e.hint } })
      }
    } catch (e) {
      if (signal.aborted) return
      set('redesign', { status: 'error', spec: null, error: { message: e.message, hint: e.hint } })
      set('visualization', { status: 'idle' })
    }
  }

  // ---------- processing / finished state ----------
  if (redesign.status !== 'idle' || visualization.status !== 'idle') {
    const planStages = [{ key: 'plan', label: 'Planning the redesigned layout', status: redesign.status === 'running' ? 'running' : redesign.status === 'done' ? 'done' : 'failed',
      detail: redesign.status === 'done' ? `${redesign.spec.changes.length} item(s) placed; Vastu conflicts ${redesign.spec.vastu.before.violated_vastu} → ${redesign.spec.vastu.after.violated_vastu}` : redesign.error?.message }]
    const vizStages = visualization.stages.length ? visualization.stages : visualization.status === 'error' ? [{ key: 'viz', label: 'Generating the redesigned room image', status: 'failed', detail: visualization.error?.message }] : []
    const done = redesign.status === 'done' && !['running', 'idle'].includes(visualization.status)
    return (
      <div className="stack" style={{ '--gap': '1.5rem' }}>
        <PageHead eyebrow="Step 8 · Redesign" title={busy ? 'Creating your redesign' : 'Your redesign is ready'}>The proposed floor plan and the room image are built from the same layout decisions.</PageHead>
        <section className="card stack" aria-label="Redesign progress"><JobProgress stages={[...planStages, ...vizStages]} title="Redesign stages" /></section>
        {redesign.status === 'error' && <Alert kind="danger" title="The redesign couldn’t be planned" action={<Button size="sm" variant="ghost" onClick={generate}>Retry</Button>}>{redesign.error.message} {redesign.error.hint}</Alert>}
        {visualization.status === 'error' && (
          <Alert kind={visualization.error.code === 'image_provider_not_configured' ? 'warn' : 'danger'}
            title={visualization.error.code === 'image_provider_not_configured' ? 'Image generation isn’t configured on this server' : 'The room image couldn’t be generated'}
            action={visualization.error.code !== 'image_provider_not_configured' && <Button size="sm" variant="ghost" onClick={generate}>Retry</Button>}>
            {visualization.error.message} {visualization.error.hint} Your redesigned floor plan is still available.
          </Alert>
        )}
        {redesign.status === 'done' && (
          <div className="card"><div className="grid cols-2"><div><h4>Proposed layout</h4><FloorPlan {...renderableFromLayout(redesign.spec.proposed_layout)} /><PlanLegend changes /></div>
            <div><h4>What changes</h4><p>{redesign.spec.summary.headline}</p><ul className="mini-list static">{redesign.spec.changes.map((c) => <li key={c.id}><span className={`chip ${c.status === 'keep' ? '' : c.status === 'moved' ? 'warn' : 'sage'}`}>{c.status}</span> {c.label}</li>)}</ul></div></div></div>
        )}
        <div className="row"><Button variant="ghost" disabled={busy} onClick={() => { set('redesign', { status: 'idle', spec: null, error: null }); set('visualization', { status: 'idle', stages: [], result: null, error: null, jobId: null }) }}>Change preferences</Button></div>
        <StepFooter back="/project/vastu" nextLabel="View results" nextDisabled={!done} onNext={() => nav('/project/results')} hint={busy ? 'Working…' : undefined} />
      </div>
    )
  }

  // ---------- preferences form ----------
  return (
    <div className="stack" style={{ '--gap': '1.5rem' }}>
      <PageHead eyebrow="Step 8 · Redesign" title="How should the room feel?">Your layout and Vastu findings are carried forward automatically. Tell us what to keep, change or add — we’ll prefer rearranging what you own before suggesting purchases.</PageHead>

      <section className="card stack"><h3>Style & palette</h3>
        <div className="style-grid" role="radiogroup" aria-label="Interior style">
          {STYLES.map((st) => (<button key={st.value} type="button" role="radio" aria-checked={prefs.style === st.value} className="style-card" onClick={() => p({ style: st.value })}><span className="swatches">{st.swatch.map((c) => <i key={c} style={{ background: c }} />)}</span><b>{st.label}</b><span className="small muted">{st.blurb}</span></button>))}
        </div>
        <div className="palette-row" role="radiogroup" aria-label="Colour palette">
          {PALETTES.map((pl) => (<button key={pl.id} type="button" role="radio" aria-checked={prefs.paletteId === pl.id} className="palette" onClick={() => p({ paletteId: pl.id })}><span className="swatches">{pl.swatch.map((c) => <i key={c} style={{ background: c }} />)}</span><span className="small">{pl.label}</span></button>))}
        </div>
        <Field label="Budget" htmlFor="b" help="Compared against indicative prices for new or replaced items only."><select id="b" className="select" value={prefs.budgetValue} onChange={(e) => p({ budgetValue: e.target.value })}>{BUDGETS.map((b) => <option key={b.value} value={b.value}>{b.label}</option>)}</select></Field>
      </section>

      <section className="card stack"><h3>Your furniture</h3>
        {placed.length === 0 ? <div className="empty">No placed furniture — the redesign will only add what you choose below.</div> : (
          <ul className="keep-list">{placed.map((f) => {
            const mode = prefs.replace.includes(f.id) ? 'replace' : 'keep'
            return (<li key={f.id}><span>{f.label}</span><div className="seg" role="group" aria-label={`${f.label}: keep or replace`}>
              <button aria-pressed={mode === 'keep'} onClick={() => p({ replace: prefs.replace.filter((x) => x !== f.id), retain: [...new Set([...prefs.retain, f.id])] })}>Keep</button>
              <button aria-pressed={mode === 'replace'} onClick={() => p({ replace: [...new Set([...prefs.replace, f.id])], retain: prefs.retain.filter((x) => x !== f.id) })}>Replace</button></div></li>)
          })}</ul>
        )}
        <div><div className="label small" style={{ fontWeight: 600, marginBottom: '.4rem' }}>Add new furniture</div>
          <div className="row">{prefs.add.map((t, i) => <button key={`${t}${i}`} className="toggle-chip" aria-pressed="true" onClick={() => p({ add: prefs.add.filter((_, k) => k !== i) })}>{CATALOG[t]?.label ?? t} ✕</button>)}
            <select className="select" style={{ width: 'auto' }} aria-label="Furniture to add" value={addPick} onChange={(e) => setAddPick(e.target.value)}>{furnitureTypes.map((t) => <option key={t} value={t}>{CATALOG[t].label}</option>)}</select>
            <Button size="sm" variant="ghost" onClick={() => p({ add: [...prefs.add, addPick] })}>Add</Button></div></div>
      </section>

      <section className="card stack"><h3>Needs & constraints</h3>
        <Field label="Storage"><div className="seg" role="group" aria-label="Storage preference">{['minimal', 'moderate', 'maximum'].map((s) => <button key={s} aria-pressed={prefs.storage === s} onClick={() => p({ storage: s })}>{s[0].toUpperCase() + s.slice(1)}</button>)}</div></Field>
        <Field label="Functional requirements"><div className="row">{FUNCTION_OPTIONS.map((o) => <button key={o} className="toggle-chip" aria-pressed={prefs.functional.includes(o)} onClick={() => p({ functional: toggle(prefs.functional, o) })}>{o}</button>)}</div></Field>
        <Field label="Accessibility & movement"><div className="row">{ACCESS_OPTIONS.map((o) => <button key={o} className="toggle-chip" aria-pressed={prefs.accessibility.includes(o)} onClick={() => p({ accessibility: toggle(prefs.accessibility, o), wheelchair: o.startsWith('Step-free') ? !prefs.accessibility.includes(o) : prefs.wheelchair })}>{o}</button>)}</div></Field>
        <Field label="Anything else?" htmlFor="notes"><textarea id="notes" className="textarea" maxLength={1500} value={prefs.notes} placeholder="e.g. keep the window area clear, add a reading chair" onChange={(e) => p({ notes: e.target.value })} /></Field>
        <label className="check"><input type="checkbox" checked={prefs.followVastu} onChange={(e) => p({ followVastu: e.target.checked })} /> Follow the Vastu recommendations <span className="muted small">(turn off to rearrange purely for space and style)</span></label>
      </section>

      <section className="card stack"><h3>Reference photo for the visualization</h3>
        <p className="small muted" style={{ margin: 0 }}>The image keeps this photo’s walls, windows and viewpoint. Choose a photo and tell us which wall of the plan it faces.</p>
        <div className="row">{photos.map((ph, i) => <button key={ph.id} className={`ref-thumb ${refPhoto?.id === ph.id ? 'on' : ''}`} onClick={() => p({ referencePhotoId: ph.id, referenceViewEdge: i === 0 ? 'top' : prefs.referenceViewEdge })} aria-pressed={refPhoto?.id === ph.id} aria-label={`Use photo ${i + 1} as the reference`}>{urls[ph.id] && <img src={urls[ph.id]} alt="" />}<span>{i === 0 ? 'Photo 1 ★' : `Photo ${i + 1}`}</span></button>)}</div>
        {refPhoto && !refIsFirst && (
          <Field label="Which wall does this photo face?"><select className="select" value={prefs.referenceViewEdge} onChange={(e) => p({ referenceViewEdge: e.target.value })}>{EDGES.map((e) => <option key={e} value={e}>{edgeCaption(e, project.orientation.topEdgeDirection)}</option>)}</select></Field>
        )}
        <p className="tiny muted" style={{ margin: 0 }}>Generated images are AI visual proposals and may not perfectly preserve the room’s geometry.</p>
      </section>
      <StepFooter back="/project/vastu" nextLabel="Generate redesign" nextIcon={<Sparkles size={16} />} onNext={generate} hint="Creates the new layout, then the room image" />
    </div>
  )
}
