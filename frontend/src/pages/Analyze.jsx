import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ScanSearch } from 'lucide-react'
import { pollJob, startAnalysisJob } from '../lib/api.js'
import { DIRECTION_LABEL, headingToCardinal } from '../lib/orientation.js'
import { useHealth } from '../lib/useHealth.js'
import { loadPhotoBlobs, useProject } from '../state/project.jsx'
import { Alert, Button, Chip, PageHead } from '../components/ui.jsx'
import JobProgress from '../components/JobProgress.jsx'
import { StepFooter } from '../components/Shell.jsx'

/** Metadata the backend job expects, built only from what the user entered/confirmed. */
export function buildAnalysisMetadata(project, useVggt) {
  const { setup, orientation: o, openings, furniture } = project
  const w = Number(setup.width), l = Number(setup.length)
  const orientation = { facing_direction: o.topEdgeDirection, facing_edge: 'top' }
  if (o.heading != null && headingToCardinal(o.heading) === o.topEdgeDirection) {
    orientation.compass_heading_degrees = o.heading
    orientation.manual_compass_direction = o.topEdgeDirection
  }
  return {
    room_type: setup.roomType, name: setup.name || undefined,
    width: w > 0 ? w : undefined, length: l > 0 ? l : undefined,
    orientation,
    openings: openings.map((x) => ({ id: x.id, type: x.type, wall: x.wall, offset: x.offset, width: x.width, is_main_entrance: !!x.is_main_entrance, provenance: 'user_provided' })),
    furniture: furniture.filter((f) => f.confirmed).map((f) => ({
      id: f.id, item: f.item, label: f.label, source: f.source === 'detected' ? 'detected' : 'user_added',
      width: f.width, length: f.length, dims_source: f.dimsSource === 'user' ? 'user' : 'default',
      ...(Number.isFinite(f.x) && Number.isFinite(f.y) ? { x: f.x, y: f.y } : {}),
    })),
    run_vggt: useVggt, run_detection: true,
  }
}

/** Fold a finished analysis result into the editable plan + furniture list. */
export function applyAnalysisResult(project, result) {
  const room = result.room
    ? { width: result.room.width, length: result.room.length, dimensionsSource: result.room.dimensions_source === 'user_provided' ? 'user_provided' : 'estimated' }
    : null
  const placed = new Map(result.placements.map((p) => [p.id, p]))
  const furniture = project.furniture.map((f) => {
    const p = placed.get(f.id)
    if (!p) return f
    return { ...f, x: p.x, y: p.y, width: p.width, length: p.length, positionSource: p.position_source === 'reconstructed' ? 'reconstructed' : 'user', confirmed: f.confirmed }
  })
  return { plan: { room, confirmed: false }, furniture }
}

export default function Analyze() {
  const { project, set, setProject, invalidate } = useProject()
  const nav = useNavigate()
  const health = useHealth()
  const ctrl = useRef(null)
  const { analysis, setup, photos, furniture, openings, orientation } = project
  const caps = health.data?.capabilities
  const vggtOk = !!caps?.geometry_reconstruction?.available
  const [useVggt, setUseVggt] = useState(true)
  const hasDims = Number(setup.width) > 0 && Number(setup.length) > 0
  const running = analysis.status === 'running'

  useEffect(() => () => ctrl.current?.abort(), [])

  const run = async () => {
    ctrl.current?.abort(); ctrl.current = new AbortController()
    const { signal } = ctrl.current
    set('analysis', { status: 'running', jobId: null, stages: [{ key: 'upload', label: 'Uploading photos', status: 'running', detail: `${photos.length} photo(s)` }], result: null, error: null })
    invalidate('analysis')
    try {
      const files = await loadPhotoBlobs(photos)
      const started = await startAnalysisJob(files, buildAnalysisMetadata(project, useVggt && vggtOk), signal)
      set('analysis', { jobId: started.job_id })
      const job = await pollJob(started.job_id, { signal, onUpdate: (j) => set('analysis', { stages: j.stages }) })
      if (job.status === 'failed') throw Object.assign(new Error(job.error?.message ?? 'The analysis failed.'), { code: job.error?.code })
      setProject((p) => ({ ...p, ...applyAnalysisResult(p, job.result), analysis: { status: 'done', jobId: started.job_id, stages: job.stages, result: job.result, error: null } }))
      nav('/project/floorplan')
    } catch (e) {
      if (signal.aborted) return
      set('analysis', { status: 'error', error: { message: e.message, hint: e.hint, code: e.code } })
    }
  }

  const manual = () => {
    set('plan', { room: { width: Number(setup.width), length: Number(setup.length), dimensionsSource: 'user_provided' }, confirmed: false })
    set('analysis', { status: 'manual', result: null, stages: [], error: null })
    nav('/project/floorplan')
  }

  return (
    <div className="stack" style={{ '--gap': '1.5rem' }}>
      <PageHead eyebrow="Step 5 · Analysis" title="Analyze the room">We’ll send your photos and confirmed details to the backend. It detects objects and — where the server supports it — estimates room geometry from the photos.</PageHead>

      <div className="grid two-col">
        <section className="card stack" aria-label="Summary of what will be analysed">
          <h3>What will be analysed</h3>
          <dl className="kv">
            <dt>Room</dt><dd>{setup.name} · {setup.roomType.replace('_', ' ')}</dd>
            <dt>Photos</dt><dd>{photos.length}</dd>
            <dt>Measurements</dt><dd>{hasDims ? <>{setup.width} × {setup.length} m <Chip kind="sage">you provided</Chip></> : <Chip kind="warn">none — estimates only</Chip>}</dd>
            <dt>Photo 1 faces</dt><dd><strong>{DIRECTION_LABEL[orientation.topEdgeDirection]}</strong> <Chip kind="sage">you confirmed</Chip></dd>
            <dt>Furniture</dt><dd>{furniture.length} item{furniture.length === 1 ? '' : 's'}</dd>
            <dt>Doors / windows</dt><dd>{openings.filter((o) => o.type === 'door').length} / {openings.filter((o) => o.type === 'window').length}</dd>
          </dl>
        </section>

        <section className="card stack" aria-label="What this server can do">
          <h3>What this server can do</h3>
          {health.status === 'loading' && <p className="small muted">Checking the backend…</p>}
          {health.status === 'error' && <Alert kind="danger" title="Can’t reach the backend" action={<Button size="sm" variant="ghost" onClick={health.retry}>Retry</Button>}>{health.error.message}</Alert>}
          {caps && (
            <ul className="caps">
              <li><Chip kind={caps.object_detection.available ? 'ok' : 'warn'}>{caps.object_detection.available ? 'Available' : 'Unavailable'}</Chip> Object detection {caps.object_detection.reason && <span className="small muted"> — {caps.object_detection.reason}</span>}</li>
              <li><Chip kind={vggtOk ? 'ok' : 'warn'}>{vggtOk ? 'Available' : 'Unavailable'}</Chip> Photo geometry (VGGT) {caps.geometry_reconstruction.reason && <span className="small muted"> — {caps.geometry_reconstruction.reason}</span>}{caps.geometry_reconstruction.note && <span className="small muted"> {caps.geometry_reconstruction.note}</span>}</li>
              <li><Chip kind={caps.image_generation.available ? 'ok' : 'warn'}>{caps.image_generation.available ? `Available (${caps.image_generation.provider})` : 'Not configured'}</Chip> Redesign visualization {caps.image_generation.reason && <span className="small muted"> — {caps.image_generation.reason}</span>}</li>
            </ul>
          )}
          {vggtOk && <label className="check"><input type="checkbox" checked={useVggt} onChange={(e) => setUseVggt(e.target.checked)} /> Estimate geometry from photos <span className="muted small">(can take several minutes on CPU)</span></label>}
          {caps && !vggtOk && <Alert kind="info" title="Geometry will come from your measurements">Without photo reconstruction you’ll place furniture on the floor plan yourself. Nothing is invented.</Alert>}
        </section>
      </div>

      {(running || analysis.stages.length > 0) && analysis.status !== 'idle' && (
        <section className="card stack" aria-label="Analysis progress">
          <h3>{running ? 'Analyzing…' : analysis.status === 'error' ? 'Analysis stopped' : 'Analysis'}</h3>
          <JobProgress stages={analysis.stages} title="Analysis stages" />
        </section>
      )}
      {analysis.status === 'error' && (
        <Alert kind="danger" title="The analysis didn’t complete" action={<Button size="sm" variant="ghost" onClick={run}>Retry</Button>}>
          {analysis.error.message}{analysis.error.hint ? ` ${analysis.error.hint}` : ''}
        </Alert>
      )}

      <div className="row">
        <Button variant="ghost" disabled={!hasDims || running} onClick={manual} title={hasDims ? '' : 'Enter room dimensions first'}>Skip analysis and build the plan manually</Button>
      </div>
      {!hasDims && <p className="small muted">Manual planning needs room dimensions — add them on the previous step.</p>}
      <StepFooter back="/project/furniture" nextIcon={<ScanSearch size={16} />} onNext={run} nextDisabled={running || health.status === 'error'}
        nextLabel={running ? 'Analyzing…' : analysis.status === 'error' ? 'Try again' : 'Analyze Room'} hint={running ? 'Working — this can take a while for large rooms' : 'Sends your photos and confirmed details to the backend'} />
    </div>
  )
}
