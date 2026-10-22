import { useMemo, useRef } from 'react'
import { C } from '../lib/theme.js'
import { colorFor, labelFor } from '../lib/furniture.js'
import { clampToRoom, round, snap } from '../lib/layout.js'
import { describeOrientation, wallZone, zoneForPoint, ZONE_LABEL } from '../lib/orientation.js'

const S = 100 // px per metre
const M = 150 // margin (room for labels, dimensions, compass)
const ZONE_ABBR = { north: 'N', north_east: 'NE', east: 'E', south_east: 'SE', south: 'S', south_west: 'SW', west: 'W', north_west: 'NW', center: '•' }
const CHANGE = C.change

/** Fit a label inside `avail` px (approximate glyph width); truncate, or hide when hopeless. */
export function fitLabel(text, avail, fs) {
  const max = Math.floor(avail / (fs * 0.58))
  if (text.length <= max) return text
  return max >= 5 ? `${text.slice(0, max - 1)}…` : ''
}


function Pill({ edge, text, x, y, rotate = 0 }) {
  const w = text.length * 11 + 26
  return (
    <g data-edge={edge} transform={`translate(${x} ${y}) rotate(${rotate})`}>
      <rect x={-w / 2} y={-14} width={w} height={28} rx={14} fill={C.sageSoft} stroke={C.sage} strokeWidth={1.2} />
      <text textAnchor="middle" dominantBaseline="central" fontSize={14} fontWeight={700} letterSpacing={1.2} fill={C.sage} fontFamily="Inter, system-ui, sans-serif" data-role="edge-label">
        {text}
      </text>
    </g>
  )
}

/** Mini compass rose; the N arrow points at the edge that faces north. */
function CompassRose({ cx, cy, northDegrees }) {
  const r = 38
  const L = { N: 0, E: 90, S: 180, W: 270 }
  return (
    <g data-role="compass-rose" aria-label={`North is toward the ${northDegrees === 0 ? 'top' : northDegrees === 90 ? 'right' : northDegrees === 180 ? 'bottom' : 'left'} of the plan`}>
      <circle cx={cx} cy={cy} r={r} fill="none" stroke={C.muted} strokeWidth={1.2} />
      {Object.entries(L).map(([k, deg]) => {
        const a = ((deg + northDegrees) * Math.PI) / 180
        const dx = Math.sin(a), dy = -Math.cos(a)
        return (
          <text key={k} x={cx + dx * (r + 16)} y={cy + dy * (r + 16)} textAnchor="middle" dominantBaseline="central"
            fontSize={k === 'N' ? 17 : 12} fontWeight={k === 'N' ? 700 : 500} fill={k === 'N' ? C.ink : C.muted} fontFamily="Inter, system-ui, sans-serif">{k}</text>
        )
      })}
      <g transform={`rotate(${northDegrees} ${cx} ${cy})`} data-role="north-arrow" data-rotation={northDegrees}>
        <path d={`M ${cx} ${cy - r + 5} L ${cx - 9} ${cy + 6} L ${cx} ${cy + 1} L ${cx + 9} ${cy + 6} Z`} fill={C.ink} />
        <path d={`M ${cx} ${cy + r - 5} L ${cx - 6} ${cy + 6} L ${cx} ${cy + 1} L ${cx + 6} ${cy + 6} Z`} fill={C.faint} />
      </g>
    </g>
  )
}

function Opening({ o, width, length, selected, onSelect, editable }) {
  const sy = (y) => (length - y) * S
  const off = o.offset, w = o.width
  let p0, p1, n
  if (o.wall === 'bottom') { p0 = [off, 0]; p1 = [off + w, 0]; n = [0, 1] }
  else if (o.wall === 'top') { p0 = [off, length]; p1 = [off + w, length]; n = [0, -1] }
  else if (o.wall === 'left') { p0 = [0, off]; p1 = [0, off + w]; n = [1, 0] }
  else { p0 = [width, off]; p1 = [width, off + w]; n = [-1, 0] }
  const A = [p0[0] * S, sy(p0[1])], B = [p1[0] * S, sy(p1[1])]
  const nv = [n[0], -n[1]] // plan normal -> svg (y flipped)
  const label = `${o.type === 'door' ? (o.is_main_entrance ? 'Main entrance door' : 'Door') : 'Window'} on the ${o.wall} wall`
  const common = {
    'data-opening': o.id, role: editable ? 'button' : undefined, tabIndex: editable ? 0 : undefined, 'aria-label': label,
    onClick: editable ? () => onSelect?.(o.id) : undefined, style: editable ? { cursor: 'pointer' } : undefined,
    onKeyDown: editable ? (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onSelect?.(o.id) } } : undefined,
  }
  const halo = selected && <line x1={A[0]} y1={A[1]} x2={B[0]} y2={B[1]} stroke={C.sage} strokeWidth={22} opacity={0.25} strokeLinecap="round" />
  if (o.type === 'window') {
    return (
      <g {...common}>
        {halo}
        <line x1={A[0]} y1={A[1]} x2={B[0]} y2={B[1]} stroke={C.paper} strokeWidth={14} />
        {[-5, 0, 5].map((k) => (
          <line key={k} x1={A[0] + nv[0] * k} y1={A[1] + nv[1] * k} x2={B[0] + nv[0] * k} y2={B[1] + nv[1] * k} stroke={C.window} strokeWidth={2.2} />
        ))}
      </g>
    )
  }
  const leaf = [A[0] + nv[0] * w * S, A[1] + nv[1] * w * S]
  const cross = (leaf[0] - A[0]) * (B[1] - A[1]) - (leaf[1] - A[1]) * (B[0] - A[0])
  const sweep = cross > 0 ? 1 : 0
  const wallMid = [(A[0] + B[0]) / 2, (A[1] + B[1]) / 2]
  const tl = Math.hypot(B[0] - A[0], B[1] - A[1]) || 1
  const tv = [(B[0] - A[0]) / tl, (B[1] - A[1]) / tl]
  const tip = [wallMid[0] - nv[0] * 8, wallMid[1] - nv[1] * 8]
  const baseC = [wallMid[0] - nv[0] * 21, wallMid[1] - nv[1] * 21]
  const tri = `${tip[0]},${tip[1]} ${baseC[0] - tv[0] * 9},${baseC[1] - tv[1] * 9} ${baseC[0] + tv[0] * 9},${baseC[1] + tv[1] * 9}`
  return (
    <g {...common}>
      {halo}
      <line x1={A[0]} y1={A[1]} x2={B[0]} y2={B[1]} stroke={C.paper} strokeWidth={14} />
      <line x1={A[0]} y1={A[1]} x2={leaf[0]} y2={leaf[1]} stroke={C.door} strokeWidth={3} />
      <path d={`M ${leaf[0]} ${leaf[1]} A ${w * S} ${w * S} 0 0 ${sweep} ${B[0]} ${B[1]}`} fill="none" stroke={C.door} strokeWidth={1.4} strokeDasharray="5 4" />
      {o.is_main_entrance && <polygon points={tri} fill={C.door} data-role="entrance-marker" />}
    </g>
  )
}

function FrontTick({ p, length }) {
  const edge = p.facingEdge || p.headboardEdge
  if (!edge) return null
  const x = p.x * S, y = (length - p.y - p.length) * S, w = p.width * S, l = p.length * S
  const seg = { top: [x + w * 0.2, y, x + w * 0.8, y], bottom: [x + w * 0.2, y + l, x + w * 0.8, y + l], left: [x, y + l * 0.2, x, y + l * 0.8], right: [x + w, y + l * 0.2, x + w, y + l * 0.8] }[edge]
  return <line x1={seg[0]} y1={seg[1]} x2={seg[2]} y2={seg[3]} stroke={C.ink} strokeWidth={p.headboardEdge ? 6 : 3} strokeLinecap="round" />
}

/**
 * Orientation-aware floor plan. EVERY direction label here is derived from
 * `topEdgeDirection` through lib/orientation.js - nothing assumes north is up.
 */
export default function FloorPlan({
  width, length, topEdgeDirection, openings = [], placements = [], estimatedDims = false,
  mode = 'view', selectedId = null, onSelect, onMove, selectedOpeningId = null, onSelectOpening,
  showZones = false, zoneStatus = {}, conflictIds = null, title, svgRef, className = '',
}) {
  const own = useRef(null)
  const ref = svgRef ?? own
  const drag = useRef(null)
  const o = useMemo(() => describeOrientation(topEdgeDirection), [topEdgeDirection])
  const editable = mode === 'edit'
  const W = width * S, H = length * S
  const vb = `${-M} ${-M} ${W + 2 * M} ${H + 2 * M}`

  const toPlan = (e) => {
    const svg = ref.current
    const pt = svg.createSVGPoint(); pt.x = e.clientX; pt.y = e.clientY
    const p = pt.matrixTransform(svg.getScreenCTM().inverse())
    return { x: p.x / S, y: length - p.y / S }
  }
  const down = (p) => (e) => {
    if (!editable) return
    onSelect?.(p.id)
    const pos = toPlan(e)
    drag.current = { id: p.id, dx: pos.x - p.x, dy: pos.y - p.y }
    e.currentTarget.setPointerCapture?.(e.pointerId)
  }
  const move = (p) => (e) => {
    if (!editable || !drag.current || drag.current.id !== p.id) return
    const pos = toPlan(e)
    const next = clampToRoom({ ...p, x: snap(pos.x - drag.current.dx), y: snap(pos.y - drag.current.dy) }, { width, length })
    onMove?.(p.id, { x: next.x, y: next.y })
  }
  const up = () => { drag.current = null }
  const key = (p) => (e) => {
    if (!editable) return
    const step = e.shiftKey ? 0.25 : 0.05
    const d = { ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, step], ArrowDown: [0, -step] }[e.key]
    if (d) {
      e.preventDefault()
      const next = clampToRoom({ ...p, x: round(p.x + d[0], 2), y: round(p.y + d[1], 2) }, { width, length })
      onMove?.(p.id, { x: next.x, y: next.y })
    } else if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onSelect?.(p.id) }
  }

  const approx = estimatedDims ? '~' : ''
  const zoneCells = showZones
    ? [-1, 0, 1].flatMap((col) => [1, 0, -1].map((row) => {
      const cx = width / 2 + (col * width) / 3, cy = length / 2 + (row * length) / 3
      const zone = zoneForPoint(cx, cy, width, length, topEdgeDirection)
      return { col, row, zone, cx, cy }
    }))
    : []

  return (
    <svg ref={ref} viewBox={vb} className={`floorplan ${className}`} role="img" xmlns="http://www.w3.org/2000/svg"
      aria-label={title ?? `Floor plan, ${width.toFixed(1)} by ${length.toFixed(1)} metres. Top edge faces ${o.edges.top}, right ${o.edges.right}, bottom ${o.edges.bottom}, left ${o.edges.left}.`}
      style={{ width: '100%', height: 'auto', touchAction: editable ? 'pan-y' : undefined, userSelect: 'none' }}>
      <rect x={-M} y={-M} width={W + 2 * M} height={H + 2 * M} fill={C.paper} />
      <rect x={0} y={0} width={W} height={H} fill={C.floor} />

      {showZones && zoneCells.map((c) => {
        const x0 = (c.cx - width / 6) * S, y0 = (length - c.cy - length / 6) * S
        const st = zoneStatus[c.zone]
        return (
          <g key={`${c.col}${c.row}`} data-zone={c.zone} pointerEvents="none">
            <rect x={x0} y={y0} width={(width / 3) * S} height={(length / 3) * S} fill={st === 'bad' ? '#b4533a' : st === 'good' ? '#6b7f5e' : 'none'} opacity={st ? 0.13 : 1} stroke={C.faint} strokeDasharray="4 6" />
            <text x={x0 + 10} y={y0 + 18} fontSize={12} fill={C.muted} fontFamily="Inter, system-ui, sans-serif" fontWeight={600}>{ZONE_ABBR[c.zone]}</text>
          </g>
        )
      })}

      {placements.map((p) => {
        const x = p.x * S, y = (length - p.y - p.length) * S, w = p.width * S, l = p.length * S
        const selected = selectedId === p.id
        const change = p.status && CHANGE[p.status]
        const estimated = p.positionSource === 'reconstructed'
        const minDim = Math.min(w, l)
        const fs = Math.max(9, Math.min(15, minDim * 0.28))
        const vertical = l > w * 1.8
        const shown = fitLabel(p.label || labelFor(p.item), (vertical ? l : w) - 8, fs)
        const zone = zoneForPoint(p.x + p.width / 2, p.y + p.length / 2, width, length, topEdgeDirection)
        return (
          <g key={p.id} data-furniture={p.id} data-zone-of-item={zone}
            role={editable ? 'button' : 'img'} tabIndex={editable ? 0 : undefined}
            aria-label={`${p.label || labelFor(p.item)}, ${p.width.toFixed(2)} by ${p.length.toFixed(2)} metres, in the ${ZONE_LABEL[zone]} zone${estimated ? ', position estimated' : ''}${editable ? '. Use arrow keys to move.' : ''}`}
            style={{ cursor: editable ? 'grab' : 'default', touchAction: editable ? 'none' : undefined }}
            onPointerDown={down(p)} onPointerMove={move(p)} onPointerUp={up} onPointerCancel={up} onKeyDown={key(p)}>
            {selected && <rect x={x - 6} y={y - 6} width={w + 12} height={l + 12} rx={6} fill="none" stroke={C.sage} strokeWidth={3} />}
            <rect x={x} y={y} width={w} height={l} rx={3} fill={colorFor(p.item)} fillOpacity={0.95}
              stroke={conflictIds?.has(p.id) ? C.danger : change || (estimated ? C.muted : C.ink)} strokeWidth={conflictIds?.has(p.id) ? 3.5 : change ? 3 : estimated ? 1.6 : 1.4}
              strokeDasharray={p.status === 'added' ? '8 5' : estimated ? '6 4' : undefined} />
            <FrontTick p={p} length={length} />
            <text x={x + w / 2} y={y + l / 2} textAnchor="middle" dominantBaseline="central" fontSize={fs} fill={C.ink} fontFamily="Inter, system-ui, sans-serif"
              transform={vertical ? `rotate(-90 ${x + w / 2} ${y + l / 2})` : undefined} pointerEvents="none">
              {shown}
            </text>
            {estimated && <text x={x + w - 5} y={y + 13} textAnchor="end" fontSize={12} fill={C.muted} pointerEvents="none">~</text>}
          </g>
        )
      })}

      <rect x={0} y={0} width={W} height={H} fill="none" stroke={C.ink} strokeWidth={7} pointerEvents="none" />
      {openings.map((op) => (
        <Opening key={op.id ?? `${op.type}-${op.wall}-${op.offset}`} o={op} width={width} length={length}
          selected={selectedOpeningId === op.id} onSelect={onSelectOpening} editable={editable && !!onSelectOpening} />
      ))}

      {/* Edge labels: directions come from the orientation mapping, never hardcoded. */}
      <Pill edge="top" text={o.edges.top.toUpperCase()} x={W / 2} y={-38} />
      <Pill edge="bottom" text={o.edges.bottom.toUpperCase()} x={W / 2} y={H + 38} />
      <Pill edge="left" text={o.edges.left.toUpperCase()} x={-38} y={H / 2} rotate={-90} />
      <Pill edge="right" text={o.edges.right.toUpperCase()} x={W + 38} y={H / 2} rotate={90} />
      <CompassRose cx={W + 82} cy={-82} northDegrees={o.northArrowDegrees} />

      {/* Dimensions */}
      <g fill={C.ink} fontFamily="Inter, system-ui, sans-serif" fontSize={15} stroke="none">
        <line x1={0} y1={H + 92} x2={W} y2={H + 92} stroke={C.muted} strokeWidth={1.2} strokeDasharray={estimatedDims ? '5 4' : undefined} />
        <line x1={0} y1={H + 84} x2={0} y2={H + 100} stroke={C.muted} strokeWidth={1.2} /><line x1={W} y1={H + 84} x2={W} y2={H + 100} stroke={C.muted} strokeWidth={1.2} />
        <text x={W / 2} y={H + 118} textAnchor="middle" fontStyle={estimatedDims ? 'italic' : 'normal'} data-role="dim-width">{approx}{width.toFixed(2)} m{estimatedDims ? ' (estimated)' : ''}</text>
        <line x1={-92} y1={0} x2={-92} y2={H} stroke={C.muted} strokeWidth={1.2} strokeDasharray={estimatedDims ? '5 4' : undefined} />
        <line x1={-100} y1={0} x2={-84} y2={0} stroke={C.muted} strokeWidth={1.2} /><line x1={-100} y1={H} x2={-84} y2={H} stroke={C.muted} strokeWidth={1.2} />
        <text transform={`translate(-112 ${H / 2}) rotate(-90)`} textAnchor="middle" fontStyle={estimatedDims ? 'italic' : 'normal'} data-role="dim-length">{approx}{length.toFixed(2)} m{estimatedDims ? ' (estimated)' : ''}</text>
        <line x1={0} y1={H + 60} x2={S} y2={H + 60} stroke={C.ink} strokeWidth={3} /><text x={S / 2} y={H + 76} textAnchor="middle" fontSize={11} fill={C.muted}>1 m</text>
      </g>
    </svg>
  )
}

export function PlanLegend({ estimated = false, changes = false }) {
  return (
    <ul className="legend" aria-label="Floor plan legend">
      <li><i className="sw" style={{ background: '#e1ddd3', border: `1.5px solid ${C.ink}` }} /> Furniture</li>
      <li><i className="sw dashed" style={{ border: `1.5px dashed ${C.muted}` }} /> Position estimated from photos</li>
      <li><i className="sw" style={{ borderTop: `3px solid ${C.door}`, height: 0 }} /> Door (swing shown; ▲ = main entrance)</li>
      <li><i className="sw" style={{ borderTop: `3px double ${C.window}`, height: 0 }} /> Window</li>
      <li><i className="sw" style={{ background: C.sageSoft, border: `1.5px solid ${C.sage}` }} /> Compass direction of each wall</li>
      {estimated && <li><i className="sw dashed" style={{ border: `1.5px dashed ${C.muted}` }} /> Dimension line dashed = estimated, not measured</li>}
      {changes && Object.entries(CHANGE).map(([k, c]) => (<li key={k}><i className="sw" style={{ border: `3px solid ${c}` }} /> {k[0].toUpperCase() + k.slice(1)}</li>))}
    </ul>
  )
}

export { wallZone }
