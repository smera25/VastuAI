/**
 * Centralised API client. All backend access goes through here.
 *
 * Base URL: VITE_API_BASE_URL if set; otherwise the SAME host as the page on port 8000
 * (so a phone that opened the dev server by LAN address reaches the backend on that machine).
 */
const envBase = import.meta.env?.VITE_API_BASE_URL
export const API_BASE = (envBase || `${globalThis.location?.protocol ?? 'http:'}//${globalThis.location?.hostname ?? 'localhost'}:8000`).replace(/\/$/, '')

export class ApiError extends Error {
  constructor(message, { status = 0, code = 'error', hint = null, details = null } = {}) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.hint = hint
    this.details = details
  }
}

/** Turn FastAPI's many error shapes (string | {code,message,hint} | {message,...} | [validation]) into an ApiError. */
export function parseErrorBody(status, body) {
  const detail = body?.detail ?? body
  if (typeof detail === 'string') return new ApiError(detail, { status })
  if (Array.isArray(detail)) {
    const msg = detail.map((d) => `${(d.loc ?? []).slice(1).join('.') || 'request'}: ${d.msg}`).slice(0, 4).join('; ')
    return new ApiError(`Some details are invalid — ${msg}`, { status, code: 'validation', details: detail })
  }
  if (detail && typeof detail === 'object') {
    return new ApiError(detail.message ?? 'Request failed', {
      status, code: detail.code ?? (detail.orientation_check ? 'orientation_conflict' : 'error'),
      hint: detail.hint ?? null, details: detail.details ?? detail.orientation_check ?? null,
    })
  }
  return new ApiError(`Request failed (${status})`, { status })
}

async function request(path, { method = 'GET', json, form, signal, timeoutMs = 60000, raw = false } = {}) {
  const ctrl = new AbortController()
  const timer = setTimeout(() => ctrl.abort(new DOMException('timeout', 'TimeoutError')), timeoutMs)
  signal?.addEventListener('abort', () => ctrl.abort(signal.reason))
  let res
  try {
    res = await fetch(`${API_BASE}${path}`, {
      method, signal: ctrl.signal,
      headers: json ? { 'Content-Type': 'application/json' } : undefined,
      body: json ? JSON.stringify(json) : form,
    })
  } catch (err) {
    if (signal?.aborted) throw err
    if (err?.name === 'TimeoutError' || ctrl.signal.reason?.name === 'TimeoutError') {
      throw new ApiError('The server took too long to respond.', { code: 'timeout' })
    }
    throw new ApiError(`Can't reach the backend at ${API_BASE}. Is it running, and is VITE_API_BASE_URL correct?`, { code: 'network' })
  } finally {
    clearTimeout(timer)
  }
  if (!res.ok) {
    let body = null
    try { body = await res.json() } catch { /* non-JSON error body */ }
    throw parseErrorBody(res.status, body)
  }
  return raw ? res : res.json()
}

export const getHealth = (signal) => request('/health', { signal, timeoutMs: 8000 })

/** Fast YOLO pass over every photo (existing endpoint) - pre-fills the furniture review. */
export function detectFurniture(files, signal) {
  const form = new FormData()
  files.forEach((f, i) => form.append('files', f, f.name || `photo-${i + 1}.jpg`))
  return request('/analyze-room-multiple', { method: 'POST', form, signal, timeoutMs: 180000 })
}

export function startAnalysisJob(files, metadata, signal) {
  const form = new FormData()
  files.forEach((f, i) => form.append('files', f, f.name || `photo-${i + 1}.jpg`))
  form.append('metadata', JSON.stringify(metadata))
  return request('/room-analysis/jobs', { method: 'POST', form, signal, timeoutMs: 120000 })
}

export const getJob = (id, signal) => request(`/jobs/${id}`, { signal, timeoutMs: 15000 })

/** Poll a REAL backend job until it finishes. `onUpdate` receives every status snapshot. */
export async function pollJob(id, { onUpdate, signal, intervalMs = 1200, maxMs = 20 * 60 * 1000 } = {}) {
  const start = Date.now()
  let failures = 0
  for (;;) {
    if (signal?.aborted) throw signal.reason ?? new DOMException('aborted', 'AbortError')
    try {
      const job = await getJob(id, signal)
      failures = 0
      onUpdate?.(job)
      if (job.status === 'succeeded' || job.status === 'failed') return job
    } catch (err) {
      if (signal?.aborted) throw err
      if (err.status === 404) throw err // job lost (server restarted)
      if (++failures >= 5) throw err
    }
    if (Date.now() - start > maxMs) throw new ApiError('Gave up waiting for the server to finish.', { code: 'timeout' })
    await new Promise((r) => setTimeout(r, intervalMs))
  }
}

export const vastuAnalyze = (layout, signal) => request('/vastu/analyze', { method: 'POST', json: { layout }, signal })
export const getVastuRules = (signal) => request('/vastu/rules', { signal })
export const planRedesign = (layout, preferences, signal) => request('/redesign/plan', { method: 'POST', json: { layout, preferences }, signal, timeoutMs: 90000 })
export const getRedesign = (id, signal) => request(`/redesign/${id}`, { signal })

export function startVisualization(redesignId, referenceBlob, signal) {
  const form = new FormData()
  if (referenceBlob) form.append('reference_image', referenceBlob, 'reference.jpg')
  return request(`/redesign/${redesignId}/visualize`, { method: 'POST', form, signal, timeoutMs: 60000 })
}

/** Server-rendered export of a structured layout. */
export async function renderFloorplan(layout, format = 'png', title) {
  const res = await request('/floorplan', { method: 'POST', json: { layout, format, title }, raw: true })
  return res.blob()
}

export const assetUrl = (path) => (path?.startsWith('http') ? path : `${API_BASE}${path}`)
export const redesignFloorplanUrl = (id, which = 'proposed', format = 'png') => `${API_BASE}/redesign/${id}/floorplan?which=${which}&format=${format}`
