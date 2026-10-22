export const ACCEPTED_TYPES = ['image/jpeg', 'image/png', 'image/webp']
export const MAX_BYTES = 10 * 1024 * 1024
export const MIN_PHOTOS = 2 // for geometry; 1 photo still allows manual layout
export const MAX_PHOTOS = 12
const MAX_SIDE = 2048

/** Client-side validation before anything is uploaded. Returns an error string or null. */
export function validateImageFile(file) {
  if (!ACCEPTED_TYPES.includes(file.type)) {
    return `${file.name || 'This file'} is not a JPG, PNG or WEBP image${file.type ? ` (it is ${file.type})` : ''}.`
  }
  if (file.size === 0) return `${file.name} is empty.`
  if (file.size > MAX_BYTES * 3) return `${file.name} is too large (${(file.size / 1048576).toFixed(1)} MB). The limit is ${MAX_BYTES / 1048576} MB.`
  return null
}

async function decode(blob) {
  if (typeof createImageBitmap === 'function') {
    try { return await createImageBitmap(blob, { imageOrientation: 'from-image' }) } catch { /* fall through */ }
  }
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(blob)
    const img = new Image()
    img.onload = () => { URL.revokeObjectURL(url); resolve(img) }
    img.onerror = () => { URL.revokeObjectURL(url); reject(new Error('The image could not be read.')) }
    img.src = url
  })
}

/**
 * Decode, apply EXIF orientation, and downscale if needed. Large phone photos are re-encoded
 * so they fit the upload limit; small ones are kept untouched.
 */
export async function prepareImage(file) {
  const problem = validateImageFile(file)
  if (problem) throw new Error(problem)
  const bmp = await decode(file)
  const w = bmp.width, h = bmp.height
  const needs = file.size > MAX_BYTES || Math.max(w, h) > 3000
  if (!needs) return { blob: file, width: w, height: h }
  const scale = Math.min(1, MAX_SIDE / Math.max(w, h))
  const c = document.createElement('canvas')
  c.width = Math.round(w * scale); c.height = Math.round(h * scale)
  c.getContext('2d').drawImage(bmp, 0, 0, c.width, c.height)
  const blob = await new Promise((res) => c.toBlob(res, 'image/jpeg', 0.9))
  if (!blob) throw new Error('The image could not be compressed.')
  if (blob.size > MAX_BYTES) throw new Error(`${file.name} is still over ${MAX_BYTES / 1048576} MB after compression.`)
  return { blob, width: c.width, height: c.height }
}

export async function blobFromVideo(video) {
  const c = document.createElement('canvas')
  c.width = video.videoWidth; c.height = video.videoHeight
  c.getContext('2d').drawImage(video, 0, 0)
  const blob = await new Promise((res) => c.toBlob(res, 'image/jpeg', 0.92))
  if (!blob) throw new Error('Could not capture a frame from the camera.')
  return { blob, width: c.width, height: c.height }
}

/** Serialise an <svg> element to a PNG blob (for "Download PNG"). */
export async function svgToPngBlob(svg, scale = 2) {
  const vb = svg.viewBox.baseVal
  const xml = new XMLSerializer().serializeToString(svg)
  const url = URL.createObjectURL(new Blob([xml], { type: 'image/svg+xml;charset=utf-8' }))
  try {
    const img = await new Promise((resolve, reject) => {
      const i = new Image(); i.onload = () => resolve(i); i.onerror = () => reject(new Error('Could not render the floor plan.')); i.src = url
    })
    const c = document.createElement('canvas')
    c.width = vb.width * scale / 2; c.height = vb.height * scale / 2
    const ctx = c.getContext('2d')
    ctx.fillStyle = '#faf7f2'; ctx.fillRect(0, 0, c.width, c.height)
    ctx.drawImage(img, 0, 0, c.width, c.height)
    return await new Promise((res) => c.toBlob(res, 'image/png'))
  } finally { URL.revokeObjectURL(url) }
}

export function downloadBlob(blob, filename) {
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob); a.download = filename
  document.body.appendChild(a); a.click(); a.remove()
  setTimeout(() => URL.revokeObjectURL(a.href), 2000)
}
