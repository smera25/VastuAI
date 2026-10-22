import { useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Download, Printer } from 'lucide-react'
import FloorPlan, { PlanLegend } from '../components/FloorPlan.jsx'
import VastuReport from '../components/VastuReport.jsx'
import { Alert, Button, Chip, PageHead, Segmented } from '../components/ui.jsx'
import { StepFooter } from '../components/Shell.jsx'
import { assetUrl, redesignFloorplanUrl } from '../lib/api.js'
import { formatInr } from '../lib/furniture.js'
import { buildLayout, renderableFromLayout } from '../lib/layout.js'
import { downloadBlob, svgToPngBlob } from '../lib/media.js'
import { DIRECTION_LABEL, describeOrientation, ZONE_LABEL } from '../lib/orientation.js'
import { usePhotoUrls, useProject } from '../state/project.jsx'

const STATUS_CHIP = { keep: '', moved: 'warn', added: 'sage', replaced: 'info' }

export default function Results() {
  const { project } = useProject()
  const nav = useNavigate()
  const urls = usePhotoUrls(project.photos)
  const [view, setView] = useState('after')
  const [slider, setSlider] = useState(50)
  const [err, setErr] = useState(null)
  const afterRef = useRef(null), beforeRef = useRef(null)
  const spec = project.redesign.spec
  const viz = project.visualization
  const o = describeOrientation(project.orientation.topEdgeDirection)
  const before = useMemo(() => renderableFromLayout(spec.source_layout), [spec])
  const after = useMemo(() => renderableFromLayout(spec.proposed_layout), [spec])
  const vastuNow = project.vastu.report
  const warnings = [
    ...(project.analysis.result?.geometry?.warnings ?? []), ...(project.analysis.result?.geometry ? [`Room geometry from photos is a partial estimate (${project.analysis.result.geometry.confidence} confidence).`] : []),
    ...(before.estimatedDims ? ['Room dimensions are estimates, not measurements.'] : []),
    ...(spec.warnings ?? []),
    ...(spec.unplaced?.length ? [`${spec.unplaced.length} item(s) could not be fitted in the redesign.`] : []),
    ...(viz.status === 'error' ? ['The room visualization could not be generated; only the floor-plan redesign is shown.'] : []),
  ]
  const budget = spec.budget
  const save = async (ref, name) => { setErr(null); try { downloadBlob(await svgToPngBlob(ref.current), name) } catch (e) { setErr(e.message) } }
  const slug = (project.setup.name || 'room').replace(/\W+/g, '-').toLowerCase()

  return (
    <div className="stack results" style={{ '--gap': '2rem' }}>
      <PageHead eyebrow="Step 9 · Results" title={`${project.setup.name || 'Your room'}: before & after`}>{spec.summary.headline}</PageHead>
      <div className="row no-print"><Segmented label="Switch layout" value={view} onChange={setView} options={[{ value: 'before', label: 'Current room' }, { value: 'after', label: 'Redesign' }, { value: 'compare', label: 'Compare' }]} />
        <span className="spacer" /><Button size="sm" variant="ghost" icon={<Printer size={14} />} onClick={() => window.print()}>Print / save as PDF report</Button></div>
      {err && <Alert kind="danger" title="Export failed">{err}</Alert>}
      {warnings.length > 0 && <Alert kind="warn" title="Please keep in mind"><ul className="tips" style={{ margin: '.3rem 0 0' }}>{[...new Set(warnings)].map((w) => <li key={w}>{w}</li>)}</ul></Alert>}

      <section aria-label="Floor plans" className="stack">
        <div className="row spread"><h3 style={{ margin: 0 }}>Floor plans</h3>
          <span className="row no-print"><Chip kind="sage">Top = {DIRECTION_LABEL[o.top]}</Chip><Chip kind="sage">North on the {o.northEdge} edge</Chip></span></div>
        {view === 'compare' && (
          <div className="compare card" style={{ '--pos': `${slider}%` }}>
            <div className="compare-stack"><div className="compare-layer"><FloorPlan {...after} /></div>
              <div className="compare-layer top" style={{ clipPath: `inset(0 ${100 - slider}% 0 0)` }}><FloorPlan {...before} /></div>
              <div className="compare-handle" style={{ left: `${slider}%` }} aria-hidden="true" /></div>
            <input type="range" min="0" max="100" value={slider} aria-label="Slide between current and redesigned layout" onChange={(e) => setSlider(+e.target.value)} className="no-print" />
            <div className="row spread tiny muted"><span>◀ Current</span><span>Redesign ▶</span></div>
          </div>
        )}
        <div className={`grid ${view === 'compare' ? 'cols-2' : ''} plans`}>
          {(view === 'before' || view === 'compare') && (<div className="card plan-card"><div className="row spread"><h4 style={{ margin: 0 }}>Current</h4><Button size="sm" variant="ghost" className="no-print" icon={<Download size={13} />} onClick={() => save(beforeRef, `${slug}-current.png`)}>PNG</Button></div><FloorPlan {...before} svgRef={beforeRef} /><PlanLegend estimated={before.estimatedDims} /></div>)}
          {(view === 'after' || view === 'compare') && (<div className="card plan-card"><div className="row spread"><h4 style={{ margin: 0 }}>Proposed</h4><span className="row no-print"><Button size="sm" variant="ghost" icon={<Download size={13} />} onClick={() => save(afterRef, `${slug}-proposed.png`)}>PNG</Button><a className="btn ghost sm" href={redesignFloorplanUrl(spec.id, 'proposed', 'pdf')} target="_blank" rel="noreferrer">PDF</a></span></div><FloorPlan {...after} svgRef={afterRef} /><PlanLegend changes /></div>)}
        </div>
      </section>

      <section aria-label="Room visualization" className="stack">
        <h3 style={{ margin: 0 }}>Redesigned room</h3>
        {viz.status === 'done' ? (
          <div className="grid cols-2 viz">
            {project.photos[0] && urls[(project.photos.find((p) => p.id === project.prefs.referencePhotoId) ?? project.photos[0]).id] && (
              <figure className="card photo-fig"><img src={urls[(project.photos.find((p) => p.id === project.prefs.referencePhotoId) ?? project.photos[0]).id]} alt="Original room photo used as reference" /><figcaption className="small muted">Your photo</figcaption></figure>)}
            <figure className="card photo-fig"><img src={assetUrl(viz.result.image_url)} alt={`AI-generated ${spec.design.style} redesign of the room`} /><figcaption className="small"><Chip kind="info">AI-generated proposal</Chip> <span className="muted">{viz.result.provider} · {viz.result.model}</span></figcaption></figure>
          </div>
        ) : (
          <Alert kind="warn" title="No room visualization for this redesign">{viz.error ? `${viz.error.message} ${viz.error.hint ?? ''}` : 'It was not generated.'} The floor plan above is the complete redesign.</Alert>
        )}
        {viz.status === 'done' && <p className="small muted">{viz.result.disclaimer}</p>}
      </section>

      <section aria-label="Your photos" className="stack"><h3 style={{ margin: 0 }}>Original photos</h3>
        <ul className="photo-grid small-grid">{project.photos.map((p, i) => <li key={p.id} className="photo">{urls[p.id] && <img src={urls[p.id]} alt={`Original photo ${i + 1}`} />}</li>)}</ul></section>

      <section aria-label="Changes" className="stack"><h3 style={{ margin: 0 }}>Furniture changes</h3>
        <div className="card table-wrap"><table className="t"><thead><tr><th>Item</th><th>Change</th><th>From</th><th>To</th></tr></thead><tbody>
          {spec.changes.map((c) => (<tr key={c.id}><td>{c.label}</td><td><Chip kind={STATUS_CHIP[c.status]}>{c.status}</Chip></td>
            <td>{c.from ? <>{ZONE_LABEL[c.from.zone]} <span className="muted">({c.from.x.toFixed(1)}, {c.from.y.toFixed(1)} m)</span></> : '—'}</td>
            <td>{ZONE_LABEL[c.to.zone]} <span className="muted">({c.to.x.toFixed(1)}, {c.to.y.toFixed(1)} m)</span></td></tr>))}
        </tbody></table></div>
        {spec.unplaced?.length > 0 && <Alert kind="warn" title="Couldn’t be fitted">{spec.unplaced.map((u) => `${u.label}: ${u.reason}`).join(' ')}</Alert>}
      </section>

      <section aria-label="Vastu" className="stack"><h3 style={{ margin: 0 }}>Vastu: before and after</h3>
        <div className="grid cols-2"><div className="card stat-card"><span className="muted small">Current layout</span><b>{spec.vastu.before.satisfied} satisfied · {spec.vastu.before.violated} to review</b></div>
          <div className="card stat-card"><span className="muted small">Proposed layout</span><b>{spec.vastu.after.satisfied} satisfied · {spec.vastu.after.violated} to review</b></div></div>
        {spec.vastu.remaining_conflicts.length > 0 && <Alert kind="info" title="Still open in the redesign">{[...new Set(spec.vastu.remaining_conflicts.map((r) => r.title))].join('; ')}. Structural items (doors, windows) usually can’t move, and some rules compete in small rooms.</Alert>}
        <details className="card"><summary>Full Vastu report for the current layout</summary>{vastuNow && <div style={{ marginTop: '1rem' }}><VastuReport report={vastuNow} /></div>}</details>
        <details className="card"><summary>Full Vastu report for the proposed layout</summary><div style={{ marginTop: '1rem' }}><VastuReport report={spec.vastu.report_after} /></div></details>
      </section>

      <section aria-label="Budget" className="card stack"><h3 style={{ margin: 0 }}>Budget</h3>
        {budget.status === 'no_purchases_needed' ? <p style={{ margin: 0 }}>{budget.note}</p> : (<>
          <p style={{ margin: 0 }}><b>{formatInr(budget.total_inr[0])} – {formatInr(budget.total_inr[1])}</b> indicative for {budget.items.length} new or replaced item(s){budget.within_budget && <> · {{ yes: 'within your budget', possibly: 'may fit your budget', no: 'above your budget' }[budget.within_budget]}</>}.</p>
          <ul className="tips">{budget.items.map((i) => <li key={i.id}>{i.label} ({i.status}): {formatInr(i.range_inr[0])} – {formatInr(i.range_inr[1])}</li>)}</ul><p className="small muted" style={{ margin: 0 }}>{budget.note}</p></>)}
      </section>
      <StepFooter back="/project/redesign" nextLabel="Start a new room" onNext={() => nav('/')} hint="Your results stay in this browser" />
    </div>
  )
}
