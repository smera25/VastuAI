import { useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Camera as CameraIcon, ImagePlus, Smartphone, Star, Trash2, Info } from 'lucide-react'
import Camera from '../components/Camera.jsx'
import { Alert, Button, PageHead } from '../components/ui.jsx'
import { StepFooter } from '../components/Shell.jsx'
import { MAX_PHOTOS, MIN_PHOTOS, prepareImage, validateImageFile } from '../lib/media.js'
import { deletePhoto, putPhoto } from '../lib/storage.js'
import { uid } from '../lib/layout.js'
import { usePhotoUrls, useProject } from '../state/project.jsx'

const SHOTS = [
  'Photo 1 · Stand near one wall and face the opposite (far) wall. This is the reference view.',
  'Photo 2 · From the same spot, turn right to the next wall.',
  'Photo 3 · Turn again so the wall behind your starting position is in frame.',
  'Photo 4 · Turn to face the remaining wall.',
  'Photo 5 · From a corner, look diagonally across the room.',
  'Photo 6 · From the opposite corner, look back diagonally.',
]
const shotHint = (i) => SHOTS[Math.min(i, SHOTS.length - 1)]

export default function Photos() {
  const { project, set, invalidate } = useProject()
  const nav = useNavigate()
  const urls = usePhotoUrls(project.photos)
  const [cameraOpen, setCameraOpen] = useState(false)
  const [problems, setProblems] = useState([])
  const [busy, setBusy] = useState(false)
  const fileInput = useRef(null)
  const nativeCam = useRef(null)
  const count = project.photos.length
  const canContinue = count >= MIN_PHOTOS

  const addBlob = async (blob, meta, name) => {
    const id = uid('photo')
    await putPhoto(id, blob)
    set('photos', (list) => [...list, { id, name, width: meta.width, height: meta.height, size: blob.size, source: meta.source }])
    invalidate('analysis'); set('detection', { status: 'idle', candidates: [], error: null, reason: null })
  }

  const addFiles = async (fileList) => {
    const files = [...fileList]
    const errs = []
    setBusy(true)
    const room = MAX_PHOTOS - count
    if (files.length > room) errs.push(`Only ${MAX_PHOTOS} photos are allowed; ${files.length - room} were skipped.`)
    for (const f of files.slice(0, Math.max(room, 0))) {
      const bad = validateImageFile(f)
      if (bad) { errs.push(bad); continue }
      try { const p = await prepareImage(f); await addBlob(p.blob, { ...p, source: 'upload' }, f.name) } catch (e) { errs.push(e.message) }
    }
    setProblems(errs); setBusy(false)
  }

  const remove = async (p) => { await deletePhoto(p.id); set('photos', (l) => l.filter((x) => x.id !== p.id)); invalidate('analysis'); set('detection', { status: 'idle', candidates: [], error: null, reason: null }) }
  const makeReference = (p) => { set('photos', (l) => [p, ...l.filter((x) => x.id !== p.id)]); invalidate('analysis') }

  return (
    <div className="stack" style={{ '--gap': '1.5rem' }}>
      <PageHead eyebrow="Step 2 · Photographs" title="Capture or upload your room">Treat every photo as a different view of the <em>same</em> room. At least {MIN_PHOTOS} overlapping photos are needed; 4–6 covering the walls and corners work best.</PageHead>

      <div className="grid two-col">
        <div className="stack">
          {cameraOpen ? (
            <Camera count={count} max={MAX_PHOTOS} shotHint={shotHint(count)} onClose={() => setCameraOpen(false)}
              onCapture={async (shot) => { await addBlob(shot.blob, { ...shot, source: 'camera' }, `camera-${count + 1}.jpg`) }} />
          ) : (
            <div className="card stack">
              <h3>Add photos</h3>
              <div className="row">
                <Button variant="sage" icon={<CameraIcon size={17} />} disabled={count >= MAX_PHOTOS} onClick={() => setCameraOpen(true)}>Use camera</Button>
                <Button variant="ghost" icon={<ImagePlus size={17} />} disabled={busy || count >= MAX_PHOTOS} onClick={() => fileInput.current.click()}>Upload photos</Button>
                <Button variant="ghost" icon={<Smartphone size={17} />} disabled={busy || count >= MAX_PHOTOS} onClick={() => nativeCam.current.click()}>Take a photo with phone camera</Button>
              </div>
              <input ref={fileInput} type="file" accept="image/jpeg,image/png,image/webp" multiple hidden aria-label="Upload photos" onChange={(e) => { addFiles(e.target.files); e.target.value = '' }} />
              <input ref={nativeCam} type="file" accept="image/*" capture="environment" hidden aria-label="Take a photo" onChange={(e) => { addFiles(e.target.files); e.target.value = '' }} />
              <div className="dropzone" onDragOver={(e) => e.preventDefault()} onDrop={(e) => { e.preventDefault(); addFiles(e.dataTransfer.files) }}>
                Drag and drop JPG, PNG or WEBP photos here <span className="muted">(max 10 MB each)</span>
              </div>
            </div>
          )}
          {problems.length > 0 && <Alert kind="warn" title="Some files were not added">{problems.join(' ')}</Alert>}
        </div>

        <aside className="card soft stack small" aria-label="How to take useful photos">
          <h4 style={{ margin: 0 }}><Info size={15} style={{ verticalAlign: '-2px' }} /> How to take useful photos</h4>
          <ul className="tips">
            <li>Stand in <b>one corner</b> and take your first photo toward the <b>opposite wall</b> — this becomes the reference view for the plan.</li>
            <li>Overlap each photo with the last by about a third so the model can relate them.</li>
            <li>Include the floor and the base of the walls; hold the phone upright and level.</li>
            <li>Capture every wall, plus doors and windows. Turn lights on and avoid motion blur.</li>
            <li>Mirrors, glass and bare white walls confuse reconstruction — include furniture and edges.</li>
          </ul>
          <p style={{ margin: 0 }}><b>Next shot:</b> {shotHint(count)}</p>
        </aside>
      </div>

      <section aria-label="Your photos" className="stack">
        <div className="row spread"><h3 style={{ margin: 0 }}>Your photos <span className="muted">({count}/{MAX_PHOTOS})</span></h3>{!canContinue && count > 0 && <span className="chip warn">Add {MIN_PHOTOS - count} more to continue</span>}</div>
        {count === 0 ? <div className="empty">No photos yet. Use the camera or upload some to get started.</div> : (
          <ul className="photo-grid">
            {project.photos.map((p, i) => (
              <li key={p.id} className="photo">
                {urls[p.id] ? <img src={urls[p.id]} alt={`Room photo ${i + 1}`} /> : <div className="photo-missing small muted">Photo not available — please re-add it.</div>}
                <div className="photo-meta">
                  <span>{i === 0 ? <span className="chip sage"><Star size={11} /> Reference</span> : `Photo ${i + 1}`}</span>
                  <span className="row" style={{ gap: '.25rem' }}>
                    {i !== 0 && <Button size="sm" variant="ghost" onClick={() => makeReference(p)} aria-label={`Make photo ${i + 1} the reference`}>Make reference</Button>}
                    <Button size="sm" variant="danger-ghost" icon={<Trash2 size={14} />} onClick={() => remove(p)} aria-label={`Remove photo ${i + 1}`}>Remove</Button>
                  </span>
                </div>
              </li>
            ))}
          </ul>
        )}
        {count > 0 && <p className="small muted">Remove a photo and retake it with the camera to replace it. The first photo defines the top of your floor plan.</p>}
      </section>
      <StepFooter back="/project/setup" next="/project/orientation" nextDisabled={!canContinue} onNext={() => nav('/project/orientation')} nextLabel="Continue to orientation"
        hint={!canContinue ? `${MIN_PHOTOS} photos minimum` : `${count} photos ready`} />
    </div>
  )
}
