import { useCallback, useEffect, useRef, useState } from 'react'
import { Camera as CameraIcon, FlipHorizontal2, X } from 'lucide-react'
import { blobFromVideo } from '../lib/media.js'
import { Alert, Button, Spinner } from './ui.jsx'

/** Explain a getUserMedia failure in plain language. */
export function describeCameraError(err) {
  const name = err?.name ?? ''
  if (!globalThis.isSecureContext) return { title: 'Live camera needs a secure connection', body: 'Browsers only allow the camera on https:// or localhost. Use “Take a photo with your phone camera” or upload existing photos instead.' }
  if (name === 'NotAllowedError' || name === 'SecurityError') return { title: 'Camera permission was denied', body: 'Allow camera access in your browser’s site settings and try again, or upload photos instead.' }
  if (name === 'NotFoundError' || name === 'OverconstrainedError') return { title: 'No camera was found', body: 'Connect a camera or upload existing photos instead.' }
  if (name === 'NotReadableError') return { title: 'The camera is busy', body: 'Another app may be using it. Close it and try again, or upload photos instead.' }
  return { title: 'The camera could not be started', body: `${err?.message ?? 'Unknown error'}. You can upload photos instead.` }
}

export default function Camera({ onCapture, onClose, shotHint, count, max }) {
  const video = useRef(null)
  const stream = useRef(null)
  const [state, setState] = useState('starting') // starting | live | error
  const [error, setError] = useState(null)
  const [facing, setFacing] = useState('environment')
  const [flash, setFlash] = useState(false)
  const [busy, setBusy] = useState(false)

  const stop = useCallback(() => { stream.current?.getTracks().forEach((t) => t.stop()); stream.current = null }, [])

  const start = useCallback(async (mode) => {
    stop(); setState('starting'); setError(null)
    try {
      if (!navigator.mediaDevices?.getUserMedia) throw Object.assign(new Error('Camera API unavailable'), { name: 'NotFoundError' })
      const s = await navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: mode }, width: { ideal: 1920 }, height: { ideal: 1440 } }, audio: false })
      stream.current = s
      if (video.current) { video.current.srcObject = s; await video.current.play().catch(() => {}) }
      setState('live')
    } catch (err) { setError(describeCameraError(err)); setState('error') }
  }, [stop])

  useEffect(() => { start(facing); return stop }, [facing, start, stop])

  const snap = async () => {
    if (!video.current?.videoWidth) return
    setBusy(true)
    try { const shot = await blobFromVideo(video.current); setFlash(true); setTimeout(() => setFlash(false), 140); await onCapture(shot) }
    catch (err) { setError({ title: 'Capture failed', body: err.message }) }
    finally { setBusy(false) }
  }

  if (state === 'error') {
    return (
      <div className="camera card stack">
        <Alert kind="warn" title={error.title}>{error.body}</Alert>
        <div className="row"><Button variant="ghost" onClick={() => start(facing)}>Try again</Button><Button variant="ghost" onClick={onClose}>Close camera</Button></div>
      </div>
    )
  }
  return (
    <div className="camera card" aria-label="Camera">
      <div className="camera-view">
        <video ref={video} playsInline muted aria-label="Live camera preview" />
        {state === 'starting' && <div className="camera-wait"><Spinner label="Starting camera" /> <span>Starting camera… allow access if your browser asks.</span></div>}
        {flash && <div className="camera-flash" />}
        {state === 'live' && shotHint && <div className="camera-hint">{shotHint}</div>}
      </div>
      <div className="row spread camera-bar">
        <Button variant="ghost" size="sm" icon={<X size={16} />} onClick={onClose}>Done</Button>
        <Button variant="sage" size="lg" icon={<CameraIcon size={18} />} disabled={state !== 'live' || busy || count >= max} onClick={snap}>
          {count >= max ? `Limit of ${max} reached` : 'Capture photo'}
        </Button>
        <Button variant="ghost" size="sm" icon={<FlipHorizontal2 size={16} />} aria-label="Switch camera" onClick={() => setFacing((f) => (f === 'environment' ? 'user' : 'environment'))} />
      </div>
      <p className="tiny muted" style={{ margin: '.5rem 0 0' }}>{count} photo{count === 1 ? '' : 's'} so far. Stay in one spot and turn slowly; keep each shot overlapping the last by about a third.</p>
    </div>
  )
}
