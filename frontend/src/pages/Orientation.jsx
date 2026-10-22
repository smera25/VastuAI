import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { DoorOpen, PanelTop, Trash2 } from 'lucide-react'
import { CompassPicker, DeviceCompass } from '../components/CompassPicker.jsx'
import FloorPlan from '../components/FloorPlan.jsx'
import { Alert, Button, Chip, PageHead } from '../components/ui.jsx'
import { StepFooter } from '../components/Shell.jsx'
import { edgeCaption, newOpening, round } from '../lib/layout.js'
import { DIRECTION_LABEL, EDGES, describeOrientation, headingToCardinal } from '../lib/orientation.js'
import { useProject } from '../state/project.jsx'

const PREVIEW_ROOM = { width: 4, length: 3.2 }
const WALL_ORDER = ['top', 'left', 'right', 'bottom']

export default function Orientation() {
  const { project, set, invalidate } = useProject()
  const nav = useNavigate()
  const { orientation: o, openings, setup } = project
  const [showHelp, setShowHelp] = useState(false)
  const room = Number(setup.width) > 0 && Number(setup.length) > 0 ? { width: Number(setup.width), length: Number(setup.length) } : PREVIEW_ROOM
  const compassCardinal = o.heading != null ? headingToCardinal(o.heading) : null
  const conflict = compassCardinal && o.topEdgeDirection && compassCardinal !== o.topEdgeDirection
  const desc = o.topEdgeDirection ? describeOrientation(o.topEdgeDirection) : null

  const change = (patch) => { set('orientation', { ...patch, confirmed: false }); invalidate('analysis') }
  const pick = (d) => change({ topEdgeDirection: d, headingSource: o.headingSource })
  const addOpening = (type) => { set('openings', (l) => [...l, newOpening(type, type === 'door' ? 'bottom' : 'top', room)]); invalidate('analysis') }
  const patchOpening = (id, patch) => { set('openings', (l) => l.map((x) => (x.id === id ? { ...x, ...patch } : x))); invalidate('analysis') }
  const removeOpening = (id) => { set('openings', (l) => l.filter((x) => x.id !== id)); invalidate('analysis') }

  return (
    <div className="stack" style={{ '--gap': '1.5rem' }}>
      <PageHead eyebrow="Step 3 · Directions" title="Which way does photo 1 face?">
        Photos can’t reveal true north, so this comes from you. The top of your floor plan is the wall photo 1 looks at — tell us its compass direction, and every label and Vastu calculation will follow.
      </PageHead>

      <div className="grid two-col">
        <div className="card stack">
          <h3>1 · Choose the direction</h3>
          <p className="small muted" style={{ margin: 0 }}>Stand where you took photo 1 and face the way the camera pointed. Which compass direction is that?</p>
          <CompassPicker value={o.topEdgeDirection} onChange={pick} heading={o.heading} />
          <DeviceCompass onReading={(h) => change({ heading: h, headingSource: 'device', topEdgeDirection: o.topEdgeDirection })} />
          {o.heading != null && !o.topEdgeDirection && (
            <Alert kind="info" title={`Your compass read ${o.heading}° (${DIRECTION_LABEL[compassCardinal]})`} action={<Button size="sm" variant="sage" onClick={() => pick(compassCardinal)}>Use {DIRECTION_LABEL[compassCardinal]}</Button>}>
              Phone compasses are easily disturbed. Pick a direction to use it — we won’t choose for you.
            </Alert>
          )}
          {conflict && (
            <Alert kind="warn" title="Your compass and your choice disagree"
              action={<span className="row"><Button size="sm" variant="ghost" onClick={() => change({ topEdgeDirection: compassCardinal })}>Use compass ({DIRECTION_LABEL[compassCardinal]})</Button><Button size="sm" variant="ghost" onClick={() => change({ heading: null, headingSource: null, topEdgeDirection: o.topEdgeDirection, note: `Compass read ${DIRECTION_LABEL[compassCardinal]} but you chose ${DIRECTION_LABEL[o.topEdgeDirection]}.` })}>Keep {DIRECTION_LABEL[o.topEdgeDirection]}</Button></span>}>
              The compass reads {o.heading}° ({DIRECTION_LABEL[compassCardinal]}) but you selected {DIRECTION_LABEL[o.topEdgeDirection]}. Decide which to trust before continuing.
            </Alert>
          )}
          <Button variant="ghost" size="sm" onClick={() => setShowHelp((s) => !s)} aria-expanded={showHelp}>{showHelp ? 'Hide' : 'Not sure which way it faces?'}</Button>
          {showHelp && (
            <div className="card soft small stack" style={{ '--gap': '.4rem' }}>
              <b>Ways to check</b>
              <ul className="tips"><li>Open a maps app or your phone’s compass while standing in the room.</li><li>Use the sun: it rises in the east and sets in the west.</li><li>Use a known landmark, such as a main road you know runs north–south.</li></ul>
              <p style={{ margin: 0 }}>You can leave this unconfirmed for now — you can’t continue until a direction is confirmed, so nothing is silently guessed.</p>
            </div>
          )}
        </div>

        <div className="card stack" aria-live="polite">
          <h3>2 · Check what it does to the plan</h3>
          {desc ? (
            <>
              <div className="preview"><FloorPlan {...room} topEdgeDirection={o.topEdgeDirection} openings={openings} placements={[]} title="Orientation preview" /></div>
              <dl className="kv">
                {EDGES.map((e) => (<div key={e} style={{ display: 'contents' }}><dt>{e[0].toUpperCase() + e.slice(1)} edge</dt><dd><strong>{DIRECTION_LABEL[desc.edges[e]]}</strong></dd></div>))}
              </dl>
              <p className="small" style={{ margin: 0 }}>North is on the <strong>{desc.northEdge}</strong> edge of the plan{desc.northEdge === 'top' ? '' : ' — not at the top'}.</p>
            </>
          ) : <div className="empty">Pick a direction to preview how the plan is labelled.</div>}
        </div>
      </div>

      <div className="card stack">
        <div className="row spread"><h3 style={{ margin: 0 }}>3 · Entrance and windows <Chip kind="dashed">approximate is fine</Chip></h3>
          <span className="row"><Button size="sm" variant="ghost" icon={<DoorOpen size={15} />} onClick={() => addOpening('door')}>Add door</Button><Button size="sm" variant="ghost" icon={<PanelTop size={15} />} onClick={() => addOpening('window')}>Add window</Button></span></div>
        <p className="small muted" style={{ margin: 0 }}>Describe where each opening is as seen from photo 1. You can fine-tune exact positions on the floor plan.</p>
        {openings.length === 0 && <div className="empty">No doors or windows recorded yet. The Vastu check will say “can’t tell yet” for entrance and light rules.</div>}
        {openings.map((op, i) => (
          <div className="opening-row" key={op.id}>
            <b>{op.type === 'door' ? 'Door' : 'Window'} {i + 1}</b>
            <select className="select" aria-label={`${op.type} ${i + 1} wall`} value={op.wall} onChange={(e) => patchOpening(op.id, { wall: e.target.value, offset: round(Math.max(0, ((e.target.value === 'top' || e.target.value === 'bottom' ? room.width : room.length) - op.width) / 2)) })}>
              {WALL_ORDER.map((w) => <option key={w} value={w}>{o.topEdgeDirection ? edgeCaption(w, o.topEdgeDirection) : { top: 'Far wall (the wall in photo 1)', left: 'Left-hand wall', right: 'Right-hand wall', bottom: 'Wall behind you' }[w]}</option>)}
            </select>
            {op.type === 'door' && <label className="check"><input type="checkbox" checked={!!op.is_main_entrance} onChange={(e) => patchOpening(op.id, { is_main_entrance: e.target.checked })} /> Main entrance</label>}
            <Button size="sm" variant="danger-ghost" icon={<Trash2 size={14} />} aria-label={`Remove ${op.type} ${i + 1}`} onClick={() => removeOpening(op.id)} />
          </div>
        ))}
      </div>

      <div className="card confirm-card">
        <label className="check big">
          <input type="checkbox" disabled={!o.topEdgeDirection || conflict} checked={o.confirmed} onChange={(e) => set('orientation', { confirmed: e.target.checked })} />
          <span>{o.topEdgeDirection ? <>I confirm that <b>photo 1 faces {DIRECTION_LABEL[o.topEdgeDirection]}</b>, so the top of the floor plan is {DIRECTION_LABEL[o.topEdgeDirection]}.</> : 'Pick a direction above to confirm it.'}</span>
        </label>
        {o.note && <p className="small muted" style={{ margin: '.5rem 0 0' }}>{o.note}</p>}
      </div>
      <StepFooter back="/project/photos" next="/project/furniture" nextDisabled={!o.confirmed} nextLabel="Continue to furniture"
        hint={!o.confirmed ? 'Confirm the direction to continue' : `Top = ${DIRECTION_LABEL[o.topEdgeDirection]}`} onNext={() => nav('/project/furniture')} />
    </div>
  )
}
