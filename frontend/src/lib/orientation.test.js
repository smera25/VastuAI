import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, it, expect } from 'vitest'
import * as o from './orientation.js'

// Same hand-written ground truth the Python suite uses.
const CASES = JSON.parse(readFileSync(resolve(__dirname, '../../../shared/orientation-cases.json'), 'utf8'))
const DIRS = ['north', 'east', 'south', 'west']

describe('orientation mapping (shared fixtures)', () => {
  it.each(CASES.top_edge_cases)('edge labels for top=$top', (c) => {
    expect(o.edgeDirections(c.top)).toEqual({ top: c.top, right: c.right, bottom: c.bottom, left: c.left })
    expect(o.northEdge(c.top)).toBe(c.north_edge)
    expect(o.northArrowRotationDegrees(c.top)).toBe(c.north_arrow_degrees)
  })

  it('brief example: top east => right south, bottom west, left north', () => {
    expect(o.edgeDirections('east')).toEqual({ top: 'east', right: 'south', bottom: 'west', left: 'north' })
  })

  it.each(DIRS)('clockwise sequence, each direction exactly once (top=%s)', (top) => {
    const e = o.edgeDirections(top)
    const seq = [e.top, e.right, e.bottom, e.left]
    const start = DIRS.indexOf(top)
    expect(seq).toEqual([0, 1, 2, 3].map((i) => DIRS[(start + i) % 4]))
    expect(new Set(seq).size).toBe(4)
  })

  it.each(DIRS)('inverse mapping round trips (top=%s)', (top) => {
    for (const [edge, dir] of Object.entries(o.edgeDirections(top))) expect(o.edgeForDirection(top, dir)).toBe(edge)
  })

  it.each(CASES.facing_cases)('facing $facing at $facing_edge', (c) => {
    expect(o.topEdgeFromFacing(c.facing, c.facing_edge)).toBe(c.expected_top)
  })

  for (const c of CASES.zone_cases) {
    for (const top of DIRS) {
      it(`zone of ${JSON.stringify(c.point)} with top=${top}`, () => {
        const { width, length } = CASES.zone_room
        expect(o.zoneForPoint(c.point[0], c.point[1], width, length, top)).toBe(c.by_top[top])
      })
    }
  }

  it.each(CASES.heading_cases)('heading $heading', (c) => {
    expect(o.headingToCardinal(c.heading)).toBe(c.cardinal)
  })

  it.each(DIRS)('planCellForZone inverts zoneForPoint (top=%s)', (top) => {
    for (const zone of o.ZONES) {
      const [col, row] = o.planCellForZone(zone, top)
      expect(o.zoneForPoint(3 + col * 2, 3 + row * 2, 6, 6, top)).toBe(zone)
    }
  })

  it('zone descriptions follow orientation', () => {
    expect(o.describePlanCell(...o.planCellForZone('north_west', 'east'))).toBe('bottom-left corner')
    expect(o.describePlanCell(...o.planCellForZone('south_east', 'east'))).toBe('top-right corner')
  })

  it('wall zones use the same mapping', () => {
    expect(o.wallZone('left', 1.5, 4, 3, 'east')).toBe('north')
    expect(o.wallZone('top', 2, 4, 3, 'east')).toBe('east')
  })

  it('rejects invalid input', () => {
    expect(() => o.normalizeDirection('up')).toThrow()
    expect(() => o.normalizeEdge('middle')).toThrow()
  })
})
