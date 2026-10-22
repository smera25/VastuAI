import { defaultSize, labelFor } from './furniture.js'
import { DIRECTION_LABEL, edgeDirections } from './orientation.js'

let counter = 0
export const uid = (prefix = 'id') => `${prefix}-${Date.now().toString(36)}${(counter++).toString(36)}${Math.random().toString(36).slice(2, 5)}`

export const round = (n, d = 3) => Math.round(n * 10 ** d) / 10 ** d
export const snap = (n, step = 0.05) => Math.round(n / step) * step
export const clamp = (n, lo, hi) => Math.min(Math.max(n, lo), hi)

export const isPlaced = (f) => Number.isFinite(f.x) && Number.isFinite(f.y)

export const rectsOverlap = (a, b, gap = 0) =>
  !(a.x + a.width + gap <= b.x || b.x + b.width + gap <= a.x || a.y + a.length + gap <= b.y || b.y + b.length + gap <= a.y)

export function clampToRoom(item, room) {
  const w = Math.min(item.width, room.width)
  const l = Math.min(item.length, room.length)
  return { width: w, length: l, x: round(clamp(item.x, 0, room.width - w)), y: round(clamp(item.y, 0, room.length - l)) }
}

export function wallLength(wall, room) {
  return wall === 'top' || wall === 'bottom' ? room.width : room.length
}

export function newFurniture(item, extra = {}) {
  const { width, length } = defaultSize(item)
  return {
    id: uid(item), item, label: labelFor(item), source: 'user_added', confirmed: true,
    width, length, dimsSource: 'default', x: null, y: null, facingEdge: null, headboardEdge: null, ...extra,
  }
}

export function newOpening(type, wall, room) {
  const width = type === 'door' ? 0.9 : 1.2
  const len = wallLength(wall, room)
  return { id: uid(type), type, wall, offset: round(Math.max(0, (len - width) / 2)), width, is_main_entrance: false, provenance: 'user_provided' }
}

/** Backend RoomLayout payload from project state. Only placed furniture is included. */
export function buildLayout(project, { furnitureOverride, nameSuffix } = {}) {
  const { plan, orientation, openings, setup } = project
  const items = (furnitureOverride ?? project.furniture).filter(isPlaced)
  return {
    room_type: setup.roomType,
    name: (setup.name || 'Room') + (nameSuffix ?? ''),
    width: plan.room.width,
    length: plan.room.length,
    dimensions_source: plan.room.dimensionsSource === 'reconstructed' ? 'reconstructed' : plan.room.dimensionsSource === 'estimated' ? 'estimated' : 'user_provided',
    orientation: { top_edge_direction: orientation.topEdgeDirection },
    openings: openings.map((o) => ({
      id: o.id, type: o.type, wall: o.wall, offset: o.offset, width: o.width,
      is_main_entrance: !!o.is_main_entrance, provenance: o.provenance === 'estimated' ? 'estimated' : 'user_provided',
    })),
    placements: items.map((f) => ({
      id: f.id, item: f.item, label: f.label, x: f.x, y: f.y, width: f.width, length: f.length,
      facing_edge: f.facingEdge || undefined, headboard_edge: f.headboardEdge || undefined,
      source: f.source === 'detected' ? 'detected' : 'user_added',
      confirmed: !!f.confirmed && f.positionSource === 'user',
      position_source: f.positionSource === 'reconstructed' ? 'reconstructed' : 'user',
      dims_source: f.dimsSource === 'user' ? 'user' : f.dimsSource === 'estimated' ? 'estimated' : 'default',
    })),
  }
}

/** Props for the SVG renderer from a backend layout dict (current or proposed). */
export function renderableFromLayout(layout) {
  return {
    width: layout.width, length: layout.length, roomType: layout.room_type,
    topEdgeDirection: layout.orientation.top_edge_direction ?? edgeTopFrom(layout.orientation),
    openings: layout.openings ?? [],
    placements: (layout.placements ?? []).map((p) => ({
      id: p.id, item: p.item, label: p.label, x: p.x, y: p.y, width: p.width, length: p.length,
      facingEdge: p.facing_edge, headboardEdge: p.headboard_edge, status: p.status, positionSource: p.position_source,
    })),
    estimatedDims: layout.dimensions_source !== 'user_provided',
  }
}
function edgeTopFrom(o) { return o.top_edge_direction ?? o.north_direction }

/** Reasons the plan cannot be confirmed yet (empty = ready). */
export function planIssues(project) {
  const issues = []
  const { plan, orientation, furniture } = project
  if (!plan.room?.width || !plan.room?.length) issues.push('Enter the room width and length.')
  if (!orientation.topEdgeDirection) issues.push('Confirm which compass direction the top of the plan faces.')
  const unplaced = furniture.filter((f) => f.confirmed && !isPlaced(f))
  if (unplaced.length) issues.push(`Place ${unplaced.length} item${unplaced.length > 1 ? 's' : ''} on the plan (or remove ${unplaced.length > 1 ? 'them' : 'it'}): ${unplaced.map((u) => u.label).join(', ')}.`)
  return issues
}

/** Human description of where a plan edge is, from photo 1's viewpoint, including its compass direction. */
export function edgeCaption(edge, topEdgeDirection) {
  const d = edgeDirections(topEdgeDirection)[edge]
  const view = { top: 'Far wall (the wall in photo 1)', right: 'Right-hand wall', bottom: 'Wall behind you', left: 'Left-hand wall' }[edge]
  return `${view} — ${DIRECTION_LABEL[d]}`
}

/** Pairs of placed items whose footprints overlap (a warning, not a hard error: the user may know better). */
export function overlappingPairs(items) {
  const placed = items.filter(isPlaced)
  const pairs = []
  for (let i = 0; i < placed.length; i++) {
    for (let j = i + 1; j < placed.length; j++) {
      if (rectsOverlap(placed[i], placed[j], -0.02)) pairs.push([placed[i], placed[j]])
    }
  }
  return pairs
}
