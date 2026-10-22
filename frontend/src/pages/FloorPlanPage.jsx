import { useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Compass, Download, Grid3x3, MousePointerClick, Pencil, RefreshCw, RotateCw, Trash2 } from 'lucide-react'
import FloorPlan, { PlanLegend } from '../components/FloorPlan.jsx'
import { Alert, Button, Chip, Field, PageHead, Provenance, Segmented, Unit } from '../components/ui.jsx'
import { StepFooter } from '../components/Shell.jsx'
import { renderFloorplan } from '../lib/api.js'
import { CATALOG, colorFor } from '../lib/furniture.js'
import { buildLayout, clampToRoom, edgeCaption, isPlaced, newOpening, overlappingPairs, planIssues, round, snap, wallLength } from '../lib/layout.js'
import { downloadBlob, svgToPngBlob } from '../lib/media.js'
import { CARDINALS, DIRECTION_LABEL, EDGES, describeOrientation } from '../lib/orientation.js'
import { useProject } from '../state/project.jsx'
import { NumInput } from '../components/NumInput.jsx'

const FACING = { desk: 'Which wall do you face while working?', stove: 'Which wall do you face while cooking?' }
const HEAD = new Set(['bed', 'single_bed'])

export default function FloorPlanPage() {
  const { project, set, invalidate } = useProject()
  const nav = useNavigate()
  const svgRef = useRef(null)
  const [mode, setMode] = useState('view')
  const [tab, setTab] = useState('items')
  const [selected, setSelected] = useState(null)
  const [selectedOpening, setSelectedOpening] = useState(null)
  const [zones, setZones] = useState(false)
  const [exportErr, setExportErr] = useState(null)
  const { plan, orientation, furniture, openings, analysis, setup } = project
  const room = plan.room
  const top = orientation.topEdgeDirection
  const issues = planIssues(project)
  const placed = furniture.filter((f) => f.confirmed && isPlaced(f))
  const unplaced = furniture.filter((f) => f.confirmed && !isPlaced(f))
  const sel = furniture.find((f) => f.id === selected)
  const selOpening = openings.find((o) => o.id === selectedOpening)
  const geometry = analysis.result?.geometry
  const overlaps = useMemo(() => overlappingPairs(placed), [placed])
  const conflictIds = useMemo(() => new Set(overlaps.flat().map((f) => f.id)), [overlaps])
  const edit = (key, fn) => { set(key, fn); invalidate('plan') }

  const renderable = useMemo(() => room && top ? {
    width: room.width, length: room.length, topEdgeDirection: top, estimatedDims: room.dimensionsSource !== 'user_provided',
    openings, placements: placed.map((f) => ({ id: f.id, item: f.item, label: f.label, x: f.x, y: f.y, width: f.width, length: f.length, facingEdge: f.facingEdge, headboardEdge: f.headboardEdge, positionSource: f.positionSource })),
  } : null, [room, top, openings, placed])

  const patchItem = (id, patch) => edit('furniture', (l) => l.map((f) => (f.id === id ? { ...f, ...patch } : f)))
  const moveItem = (id, pos) => patchItem(id, { ...pos, positionSource: 'user' })
  const setRoom = (patch) => {
    const next = { ...room, ...patch, dimensionsSource: 'user_provided' }
    if (!(next.width >= 2 && next.width <= 15 && next.length >= 2 && next.length <= 15)) return set('plan', { room: next, confirmed: false })
    set('furniture', (l) => l.map((f) => (isPlaced(f) ? { ...f, ...clampToRoom(f, next) } : f)))
    set('openings', (l) => l.map((o) => ({ ...o, width: Math.min(o.width, wallLength(o.wall, next)), offset: round(Math.min(o.offset, Math.max(0, wallLength(o.wall, next) - Math.min(o.width, wallLength(o.wall, next))))) })))
    set('plan', { room: next, confirmed: false }); invalidate('plan')
  }
  // Cascade new placements so they never stack exactly on top of each other; positions snap to the 5 cm grid.
  const placeItem = (f) => {
    const k = placed.length
    const c = clampToRoom({ ...f, x: snap(room.width / 2 - f.width / 2 + 0.3 * k), y: snap(room.length / 2 - f.length / 2 - 0.3 * k) }, room)
    patchItem(f.id, { x: round(snap(c.x), 2), y: round(snap(c.y), 2), positionSource: 'user' }); setSelected(f.id); setMode('edit')
  }
  const rotate = (f) => { const c = clampToRoom({ x: f.x, y: f.y, width: f.length, length: f.width }, room); patchItem(f.id, { width: c.width, length: c.length, x: c.x, y: c.y, dimsSource: f.dimsSource }) }

  const doExport = async (kind) => {
    setExportErr(null)
    try {
      const name = (setup.name || 'floor-plan').replace(/\W+/g, '-').toLowerCase()
      if (kind === 'png') downloadBlob(await svgToPngBlob(svgRef.current), `${name}-current.png`)
      else if (kind === 'svg') downloadBlob(new Blob([new XMLSerializer().serializeToString(svgRef.current)], { type: 'image/svg+xml' }), `${name}-current.svg`)
      else downloadBlob(await renderFloorplan(buildLayout(project), 'pdf', `${setup.name} — current layout`), `${name}-current.pdf`)
    } catch (e) { setExportErr(e.message) }
  }

  if (!room) {
    return (
      <div className="stack narrow-form" style={{ '--gap': '1.25rem' }}>
        <PageHead eyebrow="Step 6 · Floor plan" title="We need the room’s size">The analysis couldn’t determine room dimensions and none were entered. Enter measurements to draw the plan — we won’t invent them.</PageHead>
        <div className="card stack"><RoomForm room={{ width: '', length: '' }} onSet={(p) => { const w = p.width ?? 0, l = p.length ?? 0; if (w >= 2 && l >= 2) set('plan', { room: { width: w, length: l, dimensionsSource: 'user_provided' }, confirmed: false }) }} blank /></div>
        <StepFooter back="/project/analyze" nextDisabled hint="Enter dimensions to continue" />
      </div>
    )
  }

  const edgeInfo = describeOrientation(top)
  return (
    <div className="stack" style={{ '--gap': '1.25rem' }}>
      <PageHead eyebrow="Step 6 · Current floor plan" title="Check your room as it is today">
        {analysis.status === 'manual' ? 'You’re building this plan manually from your own measurements.' : 'Drag furniture, fix openings and confirm the directions. Anything marked “estimated” came from the photos or typical sizes, not from a measurement.'}
      </PageHead>

      {geometry && (
        <Alert kind={geometry.confidence === 'medium' ? 'info' : 'warn'} title={`Photo reconstruction: ${geometry.confidence} confidence — a partial estimate`}>
          {geometry.warnings.length ? geometry.warnings.join(' ') : 'Geometry was estimated from your photos; please check the outline and furniture positions.'}
        </Alert>
      )}
      {analysis.result && !geometry && analysis.result.reconstruction_unavailable_reason && (
        <Alert kind="info" title="Photo geometry wasn’t used">{analysis.result.reconstruction_unavailable_reason} The outline uses your measurements; place furniture below.</Alert>
      )}
      {analysis.result?.detections?.length === 0 && analysis.result?.warnings?.some((w) => w.startsWith('Object detection')) && null}

      <div className="actions-bar" role="toolbar" aria-label="Floor plan actions">
        <Button variant={mode === 'edit' ? 'sage' : 'ghost'} icon={<Pencil size={15} />} aria-pressed={mode === 'edit'} onClick={() => setMode((m) => (m === 'edit' ? 'view' : 'edit'))}>{mode === 'edit' ? 'Editing layout' : 'Edit Layout'}</Button>
        <Button variant="ghost" icon={<Compass size={15} />} onClick={() => { setTab('directions'); document.getElementById('panel')?.scrollIntoView({ behavior: 'smooth' }) }}>Correct Directions</Button>
        <Button variant="ghost" icon={<RefreshCw size={15} />} onClick={() => nav('/project/analyze')}>Re-analyze Room</Button>
        <Button variant={zones ? 'sage' : 'ghost'} icon={<Grid3x3 size={15} />} aria-pressed={zones} onClick={() => setZones((z) => !z)}>Vastu zones</Button>
        <span className="spacer" />
        <Button size="sm" variant="ghost" icon={<Download size={14} />} onClick={() => doExport('png')}>PNG</Button>
        <Button size="sm" variant="ghost" icon={<Download size={14} />} onClick={() => doExport('svg')}>SVG</Button>
        <Button size="sm" variant="ghost" icon={<Download size={14} />} onClick={() => doExport('pdf')}>PDF</Button>
      </div>
      {exportErr && <Alert kind="danger" title="Export failed">{exportErr}</Alert>}

      <div className="editor">
        <div className="card plan-card">
          {renderable && <FloorPlan {...renderable} svgRef={svgRef} mode={mode} selectedId={selected} onSelect={(id) => { setSelected(id); setSelectedOpening(null); if (id) setTab('items') }} onMove={moveItem}
            conflictIds={conflictIds} selectedOpeningId={selectedOpening} onSelectOpening={(id) => { setSelectedOpening(id); setSelected(null); setTab('openings') }} showZones={zones} />}
          <PlanLegend estimated={renderable?.estimatedDims} />
          {mode === 'edit' && <p className="tiny muted" style={{ margin: 0 }}><MousePointerClick size={12} style={{ verticalAlign: '-1px' }} /> Drag an item, or select it and use the arrow keys (Shift = bigger steps).</p>}
        </div>

        <div className="card panel stack" id="panel" style={{ '--gap': '.9rem' }}>
          <Segmented label="Panel" value={tab} onChange={setTab} options={[{ value: 'items', label: `Items (${furniture.filter((f) => f.confirmed).length})` }, { value: 'room', label: 'Room' }, { value: 'openings', label: 'Openings' }, { value: 'directions', label: 'Directions' }]} />

          {tab === 'items' && (
            <div className="stack" style={{ '--gap': '.8rem' }}>
              {unplaced.length > 0 && (
                <Alert kind="warn" title={`${unplaced.length} item${unplaced.length === 1 ? ' needs' : 's need'} a position`}>These weren’t located in the photos. Place each on the plan, then drag it to the right spot.</Alert>
              )}
              {unplaced.map((f) => (
                <div className="tray-item" key={f.id}><span className="f-swatch" style={{ background: colorFor(f.item) }} /><span>{f.label}</span><Button size="sm" variant="sage" onClick={() => placeItem(f)}>Place on plan</Button></div>
              ))}
              <ul className="mini-list">
                {placed.map((f) => (<li key={f.id}><button className={selected === f.id ? 'on' : ''} onClick={() => { setSelected(f.id); setMode('edit') }}><span className="f-swatch" style={{ background: colorFor(f.item) }} />{f.label}{f.positionSource === 'reconstructed' && <span className="muted"> ~</span>}</button></li>))}
              </ul>
              {sel && isPlaced(sel) ? (
                <div className="inspector stack" style={{ '--gap': '.7rem' }}>
                  <div className="row spread"><h4 style={{ margin: 0 }}>{sel.label}</h4><span className="row" style={{ gap: '.3rem' }}>{sel.positionSource === 'reconstructed' ? <Provenance kind="reconstructed" /> : <Provenance kind="user" />}</span></div>
                  <div className="grid cols-2">
                    <Field label="Left edge (x)"><Unit unit="m"><NumInput aria-label="x position in metres" value={sel.x} onCommit={(v) => moveItem(sel.id, clampToRoom({ ...sel, x: v }, room))} /></Unit></Field>
                    <Field label="Bottom edge (y)"><Unit unit="m"><NumInput aria-label="y position in metres" value={sel.y} onCommit={(v) => moveItem(sel.id, clampToRoom({ ...sel, y: v }, room))} /></Unit></Field>
                    <Field label="Width"><Unit unit="m"><NumInput aria-label="width in metres" value={sel.width} onCommit={(v) => patchItem(sel.id, { ...clampToRoom({ ...sel, width: Math.max(0.1, v) }, room), dimsSource: 'user' })} /></Unit></Field>
                    <Field label="Length"><Unit unit="m"><NumInput aria-label="length in metres" value={sel.length} onCommit={(v) => patchItem(sel.id, { ...clampToRoom({ ...sel, length: Math.max(0.1, v) }, room), dimsSource: 'user' })} /></Unit></Field>
                  </div>
                  {HEAD.has(sel.item) && <EdgeSelect label="Which wall is the headboard against?" value={sel.headboardEdge} top={top} onChange={(v) => patchItem(sel.id, { headboardEdge: v })} />}
                  {FACING[sel.item] && <EdgeSelect label={FACING[sel.item]} value={sel.facingEdge} top={top} onChange={(v) => patchItem(sel.id, { facingEdge: v })} />}
                  <div className="row"><Button size="sm" variant="ghost" icon={<RotateCw size={14} />} onClick={() => rotate(sel)}>Rotate 90°</Button>
                    <Button size="sm" variant="ghost" onClick={() => patchItem(sel.id, { x: null, y: null })}>Unplace</Button>
                    <Button size="sm" variant="danger-ghost" icon={<Trash2 size={14} />} onClick={() => { edit('furniture', (l) => l.filter((f) => f.id !== sel.id)); setSelected(null) }}>Remove</Button></div>
                </div>
              ) : <p className="small muted">Select an item on the plan, or from the list, to edit it.</p>}
            </div>
          )}

          {tab === 'room' && <RoomForm room={room} onSet={setRoom} estimated={room.dimensionsSource !== 'user_provided'} />}

          {tab === 'openings' && (
            <div className="stack" style={{ '--gap': '.8rem' }}>
              <div className="row"><Button size="sm" variant="ghost" onClick={() => { const o = newOpening('door', 'bottom', room); edit('openings', (l) => [...l, o]); setSelectedOpening(o.id) }}>Add door</Button><Button size="sm" variant="ghost" onClick={() => { const o = newOpening('window', 'top', room); edit('openings', (l) => [...l, o]); setSelectedOpening(o.id) }}>Add window</Button></div>
              {openings.length === 0 && <p className="small muted">No doors or windows yet. They’re needed for the entrance, light and door-clearance checks.</p>}
              {openings.map((o, i) => {
                const len = wallLength(o.wall, room)
                const patch = (p) => edit('openings', (l) => l.map((x) => (x.id === o.id ? { ...x, ...p } : x)))
                return (
                  <div key={o.id} className={`opening-card ${selectedOpening === o.id ? 'on' : ''}`} onClick={() => setSelectedOpening(o.id)}>
                    <div className="row spread"><b>{o.type === 'door' ? 'Door' : 'Window'} {i + 1}</b><Button size="sm" variant="danger-ghost" icon={<Trash2 size={13} />} aria-label={`Remove ${o.type} ${i + 1}`} onClick={() => edit('openings', (l) => l.filter((x) => x.id !== o.id))} /></div>
                    <select className="select" aria-label="Wall" value={o.wall} onChange={(e) => { const w = e.target.value; const L = wallLength(w, room); patch({ wall: w, width: Math.min(o.width, L), offset: round(Math.max(0, (L - Math.min(o.width, L)) / 2)) }) }}>
                      {EDGES.map((w) => <option key={w} value={w}>{edgeCaption(w, top)}</option>)}
                    </select>
                    <Field label={`Position along wall (${o.offset.toFixed(2)} m)`}><input type="range" min="0" max={Math.max(0, len - o.width)} step="0.05" value={o.offset} aria-label="Position along wall" onChange={(e) => patch({ offset: +e.target.value })} /></Field>
                    <Field label="Width"><Unit unit="m"><NumInput aria-label="Opening width in metres" value={o.width} onCommit={(v) => { const w = Math.min(Math.max(0.3, v), len); patch({ width: w, offset: Math.min(o.offset, Math.max(0, len - w)) }) }} /></Unit></Field>
                    {o.type === 'door' && <label className="check"><input type="checkbox" checked={!!o.is_main_entrance} onChange={(e) => patch({ is_main_entrance: e.target.checked })} /> Main entrance</label>}
                  </div>
                )
              })}
            </div>
          )}

          {tab === 'directions' && (
            <div className="stack" style={{ '--gap': '.8rem' }}>
              <p className="small" style={{ margin: 0 }}>Which compass direction does the <b>top of this drawing</b> point to?</p>
              <Segmented label="Direction of the top edge" value={top} onChange={(d) => { set('orientation', { topEdgeDirection: d, confirmed: true, heading: null, headingSource: null, note: 'Direction corrected on the floor plan.' }); invalidate('plan') }}
                options={CARDINALS.map((d) => ({ value: d, label: DIRECTION_LABEL[d] }))} />
              <dl className="kv">{EDGES.map((e) => <div key={e} style={{ display: 'contents' }}><dt>{e[0].toUpperCase() + e.slice(1)} edge</dt><dd><strong>{DIRECTION_LABEL[edgeInfo.edges[e]]}</strong></dd></div>)}</dl>
              <p className="small muted" style={{ margin: 0 }}>North is on the <b>{edgeInfo.northEdge}</b> edge. Changing this relabels the plan and re-evaluates every Vastu zone; furniture positions don’t move.</p>
              {orientation.note && <Chip kind="dashed">{orientation.note}</Chip>}
            </div>
          )}
        </div>
      </div>

      {overlaps.length > 0 && <Alert kind="warn" title="Some items overlap">{overlaps.map(([a, b]) => `${a.label} and ${b.label}`).join('; ')}. Check their positions or sizes (overlaps are outlined in red). You can still confirm if this is intentional.</Alert>}
      {issues.length > 0 && <Alert kind="warn" title="Before you can confirm the floor plan">{issues.join(' ')}</Alert>}
      <StepFooter back="/project/analyze" nextLabel="Confirm Floor Plan" nextDisabled={issues.length > 0}
        onNext={() => { set('plan', { confirmed: true }); nav('/project/vastu') }} hint={issues.length ? `${issues.length} thing${issues.length === 1 ? '' : 's'} to resolve` : 'Looks good? Confirm to run the Vastu check'} />
    </div>
  )
}

function EdgeSelect({ label, value, top, onChange }) {
  return (
    <Field label={label} help="Leave as “not recorded” if unsure — the rule will say it can’t be judged.">
      <select className="select" value={value ?? ''} onChange={(e) => onChange(e.target.value || null)}>
        <option value="">Not recorded</option>
        {EDGES.map((e) => <option key={e} value={e}>{edgeCaption(e, top)}</option>)}
      </select>
    </Field>
  )
}

function RoomForm({ room, onSet, estimated, blank }) {
  const [w, setW] = useState(String(room.width ?? ''))
  const [l, setL] = useState(String(room.length ?? ''))
  const bad = (v) => v !== '' && !(+v >= 2 && +v <= 15)
  const commit = (nw, nl) => { if (+nw >= 2 && +nw <= 15 && +nl >= 2 && +nl <= 15) onSet({ width: round(+nw, 2), length: round(+nl, 2) }) }
  return (
    <div className="stack" style={{ '--gap': '.8rem' }}>
      <div className="grid cols-2">
        <Field label="Width (left–right)" error={bad(w) ? '2–15 m' : null}><Unit unit="m"><input className="input" inputMode="decimal" aria-label="Room width in metres" value={w} aria-invalid={bad(w)} onChange={(e) => { setW(e.target.value); commit(e.target.value, l) }} /></Unit></Field>
        <Field label="Length (top–bottom)" error={bad(l) ? '2–15 m' : null}><Unit unit="m"><input className="input" inputMode="decimal" aria-label="Room length in metres" value={l} aria-invalid={bad(l)} onChange={(e) => { setL(e.target.value); commit(w, e.target.value) }} /></Unit></Field>
      </div>
      {!blank && (estimated ? <Alert kind="warn" title="These dimensions are estimates">Entering measured values here replaces the estimate and is used everywhere.</Alert> : <p className="small" style={{ margin: 0 }}><Provenance kind="user_provided" /></p>)}
    </div>
  )
}
