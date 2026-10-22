import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Check, Plus, RefreshCw, Trash2 } from 'lucide-react'
import { detectFurniture } from '../lib/api.js'
import { CATALOG, colorFor, defaultSize, furnitureTypes, labelFor } from '../lib/furniture.js'
import { newFurniture, uid } from '../lib/layout.js'
import { useHealth } from '../lib/useHealth.js'
import { loadPhotoBlobs, useProject } from '../state/project.jsx'
import { Alert, Button, Chip, Field, PageHead, Provenance, Spinner, Unit } from '../components/ui.jsx'
import { StepFooter } from '../components/Shell.jsx'
import { validateSetup } from './Setup.jsx'
import { NumInput } from '../components/NumInput.jsx'

function Row({ f, onPatch, onRemove }) {
  return (
    <li className={`f-row ${f.confirmed ? 'confirmed' : 'pending'}`} data-furniture-row={f.id}>
      <span className="f-swatch" style={{ background: colorFor(f.item) }} aria-hidden="true" />
      <div className="f-main">
        <div className="row" style={{ gap: '.4rem' }}>
          <select className="select compact" aria-label="Item type" value={f.item} onChange={(e) => {
            const item = e.target.value
            const patch = { item, label: f.label === labelFor(f.item) ? labelFor(item) : f.label }
            if (f.dimsSource === 'default') Object.assign(patch, defaultSize(item))
            onPatch(patch)
          }}>{furnitureTypes.map((t) => <option key={t} value={t}>{CATALOG[t].label}</option>)}</select>
          <input className="input compact" aria-label="Label" value={f.label} maxLength={40} onChange={(e) => onPatch({ label: e.target.value })} />
        </div>
        <div className="row" style={{ gap: '.4rem' }}>
          <Unit unit="m"><NumInput className="input compact num" aria-label={`${f.label} width in metres`} value={f.width} onCommit={(v) => onPatch({ width: Math.max(0.05, v), dimsSource: 'user' })} /></Unit>
          <span className="muted">×</span>
          <Unit unit="m"><NumInput className="input compact num" aria-label={`${f.label} length in metres`} value={f.length} onCommit={(v) => onPatch({ length: Math.max(0.05, v), dimsSource: 'user' })} /></Unit>
        </div>
        <div className="row" style={{ gap: '.35rem' }}>
          {f.source === 'detected' ? (f.confirmed ? <Provenance kind="user_confirmed" /> : <Provenance kind="detected" />) : <Provenance kind="user_added" />}
          <Provenance kind={f.dimsSource === 'user' ? 'user_provided' : 'default'} />
          {f.detection?.uncertain && <Chip kind="warn" title="YOLO has no stove class; ‘oven’ is only a loose match">Loose match</Chip>}
          {f.detection && <span className="tiny muted">{Math.round(f.detection.confidence * 100)}% confidence · seen in {f.detection.photos.length} photo{f.detection.photos.length === 1 ? '' : 's'}</span>}
        </div>
      </div>
      <div className="f-actions">
        {!f.confirmed && <Button size="sm" variant="sage" icon={<Check size={14} />} onClick={() => onPatch({ confirmed: true })}>Looks right</Button>}
        <Button size="sm" variant="danger-ghost" icon={<Trash2 size={14} />} aria-label={`Remove ${f.label}`} onClick={onRemove}>Remove</Button>
      </div>
    </li>
  )
}

export default function Furniture() {
  const { project, set, setProject, invalidate } = useProject()
  const nav = useNavigate()
  const health = useHealth()
  const { furniture, detection, photos, setup } = project
  const [addType, setAddType] = useState('wardrobe')
  const ctrl = useRef(null)
  const errors = validateSetup(setup)
  const pending = furniture.filter((f) => !f.confirmed)

  const runDetection = async () => {
    ctrl.current?.abort(); ctrl.current = new AbortController()
    set('detection', { status: 'running', error: null, reason: null })
    try {
      const files = await loadPhotoBlobs(photos)
      const res = await detectFurniture(files, ctrl.current.signal)
      const made = []
      for (const c of res.furniture_candidates ?? []) {
        for (let k = 0; k < c.estimated_count; k++) {
          made.push({ ...newFurniture(c.item, { id: uid(c.item), source: 'detected', confirmed: false }), detection: { confidence: c.max_confidence, photos: c.photos, uncertain: c.mapping_uncertain } })
        }
      }
      setProject((p) => ({ ...p, detection: { status: 'done', candidates: res.furniture_candidates ?? [], error: null, reason: null },
        furniture: [...p.furniture.filter((f) => f.source !== 'detected' || f.confirmed), ...made.filter((m) => !p.furniture.some((f) => f.source === 'detected' && f.confirmed && f.item === m.item))] }))
    } catch (e) {
      if (ctrl.current.signal.aborted) return
      set('detection', e.code === 'detection_unavailable' ? { status: 'unavailable', reason: e.message, error: null } : { status: 'error', error: e.message, reason: null })
    }
  }
  useEffect(() => { if (detection.status === 'idle' && photos.length) runDetection(); return () => ctrl.current?.abort() }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const patch = (id, p) => { set('furniture', (l) => l.map((f) => (f.id === id ? { ...f, ...p } : f))); invalidate('analysis') }
  const remove = (id) => { set('furniture', (l) => l.filter((f) => f.id !== id)); invalidate('analysis') }
  const add = () => { set('furniture', (l) => [...l, newFurniture(addType)]); invalidate('analysis') }

  return (
    <div className="stack" style={{ '--gap': '1.5rem' }}>
      <PageHead eyebrow="Step 4 · Furniture & measurements" title="What’s in the room?">Review what we found, correct it, and add anything missing. Sizes shown are typical defaults until you enter real measurements — they are estimates, not measurements.</PageHead>

      {detection.status === 'running' && <Alert kind="info" title="Detecting objects in your photos"><span className="row"><Spinner /> Running object detection on {photos.length} photo{photos.length === 1 ? '' : 's'}…</span></Alert>}
      {detection.status === 'unavailable' && <Alert kind="warn" title="Automatic detection isn’t available on this server">{detection.reason} Add your furniture manually below.</Alert>}
      {detection.status === 'error' && <Alert kind="danger" title="Detection failed" action={<Button size="sm" variant="ghost" onClick={runDetection}>Retry</Button>}>{detection.error}</Alert>}
      {detection.status === 'done' && detection.candidates.length === 0 && <Alert kind="info" title="No common furniture was recognised">Detection covers items like beds, sofas, chairs, tables, TVs, fridges, sinks and plants. Add everything else below.</Alert>}
      {health.status === 'error' && detection.status !== 'running' && <Alert kind="warn" title="Backend not reachable" action={<Button size="sm" variant="ghost" onClick={health.retry}>Retry</Button>}>{health.error.message}</Alert>}

      <div className="grid two-col">
        <section className="card stack" aria-label="Furniture and fixtures">
          <div className="row spread"><h3 style={{ margin: 0 }}>Furniture <span className="muted">({furniture.length})</span></h3>
            <span className="row">
              {pending.length > 0 && <Button size="sm" variant="sage" onClick={() => set('furniture', (l) => l.map((f) => ({ ...f, confirmed: true })))}>Confirm all ({pending.length})</Button>}
              {photos.length > 0 && <Button size="sm" variant="ghost" icon={<RefreshCw size={14} />} disabled={detection.status === 'running'} onClick={runDetection}>Re-detect</Button>}
            </span></div>
          {furniture.length === 0 ? <div className="empty">Nothing here yet. Add your first item below.</div> : (
            <ul className="f-list">{furniture.map((f) => <Row key={f.id} f={f} onPatch={(p) => patch(f.id, p)} onRemove={() => remove(f.id)} />)}</ul>
          )}
          <div className="row add-row">
            <select className="select" aria-label="Item to add" value={addType} onChange={(e) => setAddType(e.target.value)}>{furnitureTypes.map((t) => <option key={t} value={t}>{CATALOG[t].label}</option>)}</select>
            <Button variant="ghost" icon={<Plus size={16} />} onClick={add}>Add item</Button>
          </div>
          <p className="tiny muted" style={{ margin: 0 }}>Doors and windows are added on the orientation step and the floor plan. Detection does not recognise wardrobes, desks or stoves, so add those yourself.</p>
        </section>

        <section className="card stack" aria-label="Room measurements">
          <h3>Room measurements</h3>
          <div className="grid cols-2">
            <Field label="Width" htmlFor="rw" error={errors.width}><Unit unit="m"><input id="rw" className="input" inputMode="decimal" value={setup.width} onChange={(e) => { set('setup', { width: e.target.value }); invalidate('analysis') }} /></Unit></Field>
            <Field label="Length" htmlFor="rl" error={errors.length}><Unit unit="m"><input id="rl" className="input" inputMode="decimal" value={setup.length} onChange={(e) => { set('setup', { length: e.target.value }); invalidate('analysis') }} /></Unit></Field>
          </div>
          {Number(setup.width) > 0 && Number(setup.length) > 0
            ? <p className="small" style={{ margin: 0 }}><Provenance kind="user_provided" /> These will calibrate the photo analysis and draw the room outline.</p>
            : <Alert kind="info" title="No measurements entered">If you leave this blank, the size comes only from the photos and will be labelled as a rough estimate.</Alert>}
        </section>
      </div>
      <StepFooter back="/project/orientation" next="/project/analyze" nextLabel="Continue to analysis" nextDisabled={pending.length > 0 || Object.keys(errors).length > 0}
        onNext={() => nav('/project/analyze')} hint={pending.length ? `Confirm or remove ${pending.length} auto-detected item${pending.length === 1 ? '' : 's'}` : Object.keys(errors).length ? 'Fix the room measurements' : `${furniture.length} item${furniture.length === 1 ? '' : 's'} confirmed`} />
    </div>
  )
}
