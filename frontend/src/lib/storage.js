/** Persistence: photo blobs in IndexedDB (too big for localStorage), project JSON in localStorage. */
const DB = 'vastu-atelier'
const STORE = 'photos'
const KEY = 'vastu-atelier:project:v1'
const memory = new Map() // fallback when IndexedDB is unavailable (e.g. some private modes)

function openDb() {
  return new Promise((resolve, reject) => {
    if (typeof indexedDB === 'undefined') return reject(new Error('no indexedDB'))
    const req = indexedDB.open(DB, 1)
    req.onupgradeneeded = () => req.result.createObjectStore(STORE)
    req.onsuccess = () => resolve(req.result)
    req.onerror = () => reject(req.error)
  })
}

async function tx(mode, fn) {
  const db = await openDb()
  return new Promise((resolve, reject) => {
    const t = db.transaction(STORE, mode)
    const result = fn(t.objectStore(STORE))
    t.oncomplete = () => resolve(result?.result)
    t.onerror = () => reject(t.error)
  })
}

export async function putPhoto(id, blob) {
  memory.set(id, blob)
  try { await tx('readwrite', (s) => s.put(blob, id)) } catch { /* kept in memory for this session */ }
}
export async function getPhoto(id) {
  if (memory.has(id)) return memory.get(id)
  try { const b = await tx('readonly', (s) => s.get(id)); if (b) memory.set(id, b); return b ?? null } catch { return null }
}
export async function deletePhoto(id) {
  memory.delete(id)
  try { await tx('readwrite', (s) => s.delete(id)) } catch { /* ignore */ }
}
export async function clearPhotos() {
  memory.clear()
  try { await tx('readwrite', (s) => s.clear()) } catch { /* ignore */ }
}

export function loadProject() {
  try { const raw = localStorage.getItem(KEY); return raw ? JSON.parse(raw) : null } catch { return null }
}
export function saveProject(project) {
  try { localStorage.setItem(KEY, JSON.stringify(project)) } catch { /* quota or disabled: continue without persistence */ }
}
export function clearProject() {
  try { localStorage.removeItem(KEY) } catch { /* ignore */ }
}
