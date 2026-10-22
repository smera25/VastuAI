/**
 * Orientation mapping - JavaScript mirror of backend `app/orientation.py`.
 *
 * Single source of truth on the frontend for relating a drawn floor plan's
 * edges to compass directions. Every label, arrow, zone and request payload
 * goes through here. Tested against the SAME fixtures as the backend
 * (shared/orientation-cases.json).
 *
 * Plan convention: x right, y up, bird's-eye view. `topEdgeDirection` is the
 * compass direction the TOP edge of the drawing represents. Around the room the
 * compass order is always clockwise: top -> right -> bottom -> left.
 *
 *   topEdgeDirection = 'east'  =>  top east, right south, bottom west, left NORTH
 */

export const CARDINALS = ['north', 'east', 'south', 'west'] // clockwise
export const EDGES = ['top', 'right', 'bottom', 'left'] // clockwise
export const ZONES = ['north', 'north_east', 'east', 'south_east', 'south', 'south_west', 'west', 'north_west', 'center']

const COMPASS_VECTORS = [[0, 1], [1, 0], [0, -1], [-1, 0]] // (east, north), aligned with CARDINALS
const ZONE_BY_SIGNS = {
  '0,1': 'north', '1,1': 'north_east', '1,0': 'east', '1,-1': 'south_east', '0,-1': 'south',
  '-1,-1': 'south_west', '-1,0': 'west', '-1,1': 'north_west', '0,0': 'center',
}

export const DIRECTION_LABEL = { north: 'North', east: 'East', south: 'South', west: 'West' }
export const ZONE_LABEL = {
  north: 'North', north_east: 'North-East', east: 'East', south_east: 'South-East', south: 'South',
  south_west: 'South-West', west: 'West', north_west: 'North-West', center: 'Centre',
}
export const EDGE_LABEL = { top: 'Top', right: 'Right', bottom: 'Bottom', left: 'Left' }

export function normalizeDirection(d) {
  const v = String(d ?? '').trim().toLowerCase()
  if (!CARDINALS.includes(v)) throw new Error(`Direction must be one of ${CARDINALS.join(', ')}; got ${JSON.stringify(d)}.`)
  return v
}

export function normalizeEdge(e) {
  const v = String(e ?? '').trim().toLowerCase()
  if (!EDGES.includes(v)) throw new Error(`Edge must be one of ${EDGES.join(', ')}; got ${JSON.stringify(e)}.`)
  return v
}

const mod4 = (n) => ((n % 4) + 4) % 4

export function rotateDirection(direction, quarterTurns) {
  return CARDINALS[mod4(CARDINALS.indexOf(normalizeDirection(direction)) + quarterTurns)]
}

/** Compass direction of each drawn edge. */
export function edgeDirections(topEdgeDirection) {
  const top = normalizeDirection(topEdgeDirection)
  return { top, right: rotateDirection(top, 1), bottom: rotateDirection(top, 2), left: rotateDirection(top, 3) }
}

/** Which drawn edge faces `direction` (inverse of edgeDirections). */
export function edgeForDirection(topEdgeDirection, direction) {
  const t = CARDINALS.indexOf(normalizeDirection(topEdgeDirection))
  const d = CARDINALS.indexOf(normalizeDirection(direction))
  return EDGES[mod4(d - t)]
}

export const northEdge = (top) => edgeForDirection(top, 'north')

/** Clockwise degrees from "pointing up the page" to "pointing at north". */
export const northArrowRotationDegrees = (top) => (EDGES.indexOf(northEdge(top)) * 90) % 360

/** Top edge direction from what the user faces and which drawn edge that wall is. */
export function topEdgeFromFacing(facingDirection, facingEdge = 'top') {
  return rotateDirection(facingDirection, -EDGES.indexOf(normalizeEdge(facingEdge)))
}

export function headingToCardinal(heading) {
  return CARDINALS[Math.floor((((heading % 360) + 360) % 360 + 45) / 90) % 4]
}

/** Plan offset (dx right, dy up) -> [east, north]. */
export function planOffsetToCompass(dx, dy, top) {
  const t = CARDINALS.indexOf(normalizeDirection(top))
  const [ue, un] = COMPASS_VECTORS[t]
  const [re, rn] = COMPASS_VECTORS[mod4(t + 1)]
  return [dx * re + dy * ue, dx * rn + dy * un]
}

const sign = (v, tol) => (v > tol ? 1 : v < -tol ? -1 : 0)

/** Vastu zone of a plan point (3x3 grid mapped through the orientation). */
export function zoneForPoint(x, y, roomWidth, roomLength, top) {
  const col = sign(x - roomWidth / 2, roomWidth / 6)
  const row = sign(y - roomLength / 2, roomLength / 6)
  const [e, n] = planOffsetToCompass(col, row, top)
  return ZONE_BY_SIGNS[`${e},${n}`]
}

/** Inverse: which 3x3 cell [col,row] (-1/0/1) holds a zone. */
export function planCellForZone(zone, top) {
  for (const col of [-1, 0, 1]) {
    for (const row of [-1, 0, 1]) {
      const [e, n] = planOffsetToCompass(col, row, top)
      if (ZONE_BY_SIGNS[`${e},${n}`] === zone) return [col, row]
    }
  }
  throw new Error(`Unknown zone ${zone}`)
}

export function describePlanCell(col, row) {
  if (col === 0 && row === 0) return 'centre of the room'
  const v = { 1: 'top', '-1': 'bottom', 0: '' }[row]
  const h = { 1: 'right', '-1': 'left', 0: '' }[col]
  return v && h ? `${v}-${h} corner` : `${v || h} side`
}

/** Zone of a point `offset` metres along a wall. */
export function wallZone(edge, offset, roomWidth, roomLength, top) {
  switch (normalizeEdge(edge)) {
    case 'top': return zoneForPoint(offset, roomLength, roomWidth, roomLength, top)
    case 'bottom': return zoneForPoint(offset, 0, roomWidth, roomLength, top)
    case 'left': return zoneForPoint(0, offset, roomWidth, roomLength, top)
    default: return zoneForPoint(roomWidth, offset, roomWidth, roomLength, top)
  }
}

/** Everything the UI needs to know about one orientation. */
export function describeOrientation(top) {
  const edges = edgeDirections(top)
  return { top: edges.top, edges, northEdge: northEdge(top), northArrowDegrees: northArrowRotationDegrees(top) }
}

/** How the plan's edges read from the reference photo's viewpoint (standing at the bottom edge looking at the top edge). */
export const VIEW_WALL = { top: 'far wall', right: 'right wall', bottom: 'wall behind you', left: 'left wall' }
