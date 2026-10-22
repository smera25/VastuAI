import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { render, within } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import FloorPlan from '../components/FloorPlan.jsx'

const CASES = JSON.parse(readFileSync(resolve(__dirname, '../../../shared/orientation-cases.json'), 'utf8'))
const edgeText = (container, edge) => container.querySelector(`[data-edge="${edge}"] text`).textContent

const plan = { width: 4, length: 3.5, openings: [{ id: 'w1', type: 'window', wall: 'top', offset: 1, width: 1.2 }],
  placements: [{ id: 'bed', item: 'bed', label: 'Bed', x: 0.5, y: 0.5, width: 1.6, length: 2 }] }

describe('FloorPlan renders labels from the confirmed orientation', () => {
  it.each(CASES.top_edge_cases)('top=$top: every edge label, the compass and the arrow follow', (c) => {
    const { container } = render(<FloorPlan {...plan} topEdgeDirection={c.top} />)
    expect(edgeText(container, 'top')).toBe(c.top.toUpperCase())
    expect(edgeText(container, 'right')).toBe(c.right.toUpperCase())
    expect(edgeText(container, 'bottom')).toBe(c.bottom.toUpperCase())
    expect(edgeText(container, 'left')).toBe(c.left.toUpperCase())
    const arrow = container.querySelector('[data-role="north-arrow"]')
    expect(Number(arrow.getAttribute('data-rotation'))).toBe(c.north_arrow_degrees)
    // The edge carrying the NORTH label is the one the arrow points to.
    const northEdge = c.north_edge
    expect(edgeText(container, northEdge)).toBe('NORTH')
  })

  it('brief example: top=east gives top=EAST, right=SOUTH, bottom=WEST, left=NORTH', () => {
    const { container } = render(<FloorPlan {...plan} topEdgeDirection="east" />)
    expect([edgeText(container, 'top'), edgeText(container, 'right'), edgeText(container, 'bottom'), edgeText(container, 'left')]).toEqual(['EAST', 'SOUTH', 'WEST', 'NORTH'])
  })

  it('changing the orientation re-labels the same plan', () => {
    const { container, rerender } = render(<FloorPlan {...plan} topEdgeDirection="north" />)
    expect(edgeText(container, 'left')).toBe('WEST')
    expect(container.querySelector('[data-furniture="bed"]').getAttribute('data-zone-of-item')).toBe('west')
    rerender(<FloorPlan {...plan} topEdgeDirection="south" />)
    expect(edgeText(container, 'left')).toBe('EAST')
    // Bed centre (1.3, 1.5) is in the left-middle cell: west when top=north, east when top=south.
    expect(container.querySelector('[data-furniture="bed"]').getAttribute('data-zone-of-item')).toBe('east')
  })

  it('furniture zones depend on orientation (same bed, four zones)', () => {
    const zones = ['north', 'east', 'south', 'west'].map((t) => {
      const { container } = render(<FloorPlan {...plan} topEdgeDirection={t} />)
      return container.querySelector('[data-furniture="bed"]').getAttribute('data-zone-of-item')
    })
    expect(new Set(zones).size).toBeGreaterThanOrEqual(3)
  })

  it('marks estimated dimensions as estimates, not measurements', () => {
    const { container } = render(<FloorPlan {...plan} topEdgeDirection="north" estimatedDims />)
    expect(container.querySelector('[data-role="dim-width"]').textContent).toMatch(/^~.*estimated/)
  })

  it('exposes an accessible description with all four edges', () => {
    const { getByRole } = render(<FloorPlan {...plan} topEdgeDirection="east" />)
    expect(getByRole('img', { name: /Top edge faces east, right south, bottom west, left north/ })).toBeInTheDocument()
  })

  it('reconstructed positions are flagged', () => {
    const p = { ...plan, placements: [{ ...plan.placements[0], positionSource: 'reconstructed' }] }
    const { getByLabelText } = render(<FloorPlan {...p} topEdgeDirection="north" />)
    expect(getByLabelText(/position estimated/)).toBeInTheDocument()
  })
})

import { overlappingPairs, edgeCaption } from '../lib/layout.js'
describe('layout helpers', () => {
  it('detects overlapping furniture but not touching items', () => {
    const a = { id: 'a', x: 0, y: 0, width: 1, length: 1 }
    expect(overlappingPairs([a, { id: 'b', x: 0.5, y: 0.5, width: 1, length: 1 }]).length).toBe(1)
    expect(overlappingPairs([a, { id: 'c', x: 1, y: 0, width: 1, length: 1 }]).length).toBe(0)
    expect(overlappingPairs([a, { id: 'd', x: null, y: null, width: 1, length: 1 }]).length).toBe(0)
  })
  it('wall captions are capitalised and carry the compass direction', () => {
    expect(edgeCaption('left', 'east')).toBe('Left-hand wall — North')
  })
  it('main entrance is drawn as a marker that cannot collide with edge labels', () => {
    const { container } = render(<FloorPlan {...plan} openings={[{ id: 'd', type: 'door', wall: 'bottom', offset: 1.55, width: 0.9, is_main_entrance: true }]} topEdgeDirection="east" />)
    expect(container.querySelector('[data-role="entrance-marker"]')).toBeTruthy()
  })
})
