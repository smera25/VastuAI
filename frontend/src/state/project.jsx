import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'
import { clearPhotos, clearProject, getPhoto, loadProject, saveProject } from '../lib/storage.js'
import { uid } from '../lib/layout.js'

export const defaultPrefs = () => ({
  style: 'modern', paletteId: 'warm-neutrals', budgetValue: '', retain: [], replace: [], add: [],
  storage: 'moderate', functional: [], accessibility: [], wheelchair: false, notes: '', followVastu: true,
  referencePhotoId: null, referenceViewEdge: 'top',
})

export const createProject = () => ({
  version: 1, id: uid('room'), createdAt: Date.now(),
  setup: { name: '', roomType: 'bedroom', width: '', length: '', style: 'modern', budgetValue: '' },
  photos: [], // {id,name,width,height,size,source}; the bytes live in IndexedDB
  orientation: { topEdgeDirection: null, heading: null, headingSource: null, confirmed: false, note: null },
  openings: [],
  furniture: [],
  detection: { status: 'idle', candidates: [], error: null, reason: null },
  analysis: { status: 'idle', jobId: null, stages: [], result: null, error: null },
  plan: { room: null, confirmed: false },
  vastu: { status: 'idle', report: null, error: null },
  prefs: defaultPrefs(),
  redesign: { status: 'idle', spec: null, error: null },
  visualization: { status: 'idle', jobId: null, stages: [], result: null, error: null },
})

/** Which downstream results become stale when an upstream stage changes. */
const DOWNSTREAM = {
  analysis: ['plan', 'vastu', 'redesign', 'visualization'],
  plan: ['vastu', 'redesign', 'visualization'],
  vastu: ['redesign', 'visualization'],
  redesign: ['visualization'],
}
const RESET = {
  plan: (p) => ({ ...p.plan, confirmed: false }),
  vastu: () => ({ status: 'idle', report: null, error: null }),
  redesign: () => ({ status: 'idle', spec: null, error: null }),
  visualization: () => ({ status: 'idle', jobId: null, stages: [], result: null, error: null }),
}

const Ctx = createContext(null)

function hydrate() {
  const saved = loadProject()
  if (!saved || saved.version !== 1) return createProject()
  const base = createProject()
  // Never resume a half-finished network operation from a previous page load.
  const settle = (s) => (s?.status === 'running' ? { ...s, status: 'idle', stages: [], jobId: null } : s)
  return { ...base, ...saved, analysis: settle(saved.analysis), visualization: settle(saved.visualization),
    redesign: settle(saved.redesign), vastu: settle(saved.vastu), detection: settle(saved.detection),
    prefs: { ...base.prefs, ...saved.prefs } }
}

export function ProjectProvider({ children }) {
  const [project, setProjectState] = useState(hydrate)
  const timer = useRef()

  useEffect(() => {
    clearTimeout(timer.current)
    timer.current = setTimeout(() => saveProject(project), 250)
    return () => clearTimeout(timer.current)
  }, [project])

  const setProject = useCallback((fn) => setProjectState((p) => (typeof fn === 'function' ? fn(p) : fn)), [])

  /** set('setup', {...patch}) merges objects; set('photos', array) replaces; accepts updater functions. */
  const set = useCallback((key, value) => setProjectState((p) => {
    const next = typeof value === 'function' ? value(p[key]) : value
    const merged = Array.isArray(next) || next === null || typeof next !== 'object' ? next : { ...p[key], ...next }
    return { ...p, [key]: merged }
  }), [])

  /** Mark everything downstream of `stage` stale (e.g. editing the plan invalidates Vastu + redesign). */
  const invalidate = useCallback((stage) => setProjectState((p) => {
    const out = { ...p }
    for (const k of DOWNSTREAM[stage] ?? []) out[k] = RESET[k](p)
    return out
  }), [])

  const reset = useCallback(async () => {
    await clearPhotos(); clearProject()
    setProjectState(createProject())
  }, [])

  const value = useMemo(() => ({ project, set, setProject, invalidate, reset }), [project, set, setProject, invalidate, reset])
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export const useProject = () => {
  const v = useContext(Ctx)
  if (!v) throw new Error('useProject must be used inside <ProjectProvider>')
  return v
}

/** Object URLs for the stored photos (revoked on change/unmount). */
export function usePhotoUrls(photos) {
  const [urls, setUrls] = useState({})
  const key = photos.map((p) => p.id).join('|')
  useEffect(() => {
    let alive = true
    const made = []
    ;(async () => {
      const next = {}
      for (const p of photos) {
        const blob = await getPhoto(p.id)
        if (blob) { const u = URL.createObjectURL(blob); made.push(u); next[p.id] = u }
      }
      if (alive) setUrls(next)
    })()
    return () => { alive = false; made.forEach(URL.revokeObjectURL) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key])
  return urls
}

/** Fetch the stored photo blobs in order (for upload). */
export async function loadPhotoBlobs(photos) {
  const blobs = []
  for (const p of photos) {
    const b = await getPhoto(p.id)
    if (!b) throw new Error(`Photo "${p.name}" is no longer available in this browser. Please re-add it.`)
    blobs.push(new File([b], p.name, { type: b.type || 'image/jpeg' }))
  }
  return blobs
}
