/** The wizard sequence, in the required order. */
export const STEPS = [
  { path: '/project/setup', label: 'Room' },
  { path: '/project/photos', label: 'Photos' },
  { path: '/project/orientation', label: 'Orientation' },
  { path: '/project/furniture', label: 'Furniture' },
  { path: '/project/analyze', label: 'Analyze' },
  { path: '/project/floorplan', label: 'Floor plan' },
  { path: '/project/vastu', label: 'Vastu' },
  { path: '/project/redesign', label: 'Redesign' },
  { path: '/project/results', label: 'Results' },
]

/** Prerequisite check per step: returns a message when the user can't be here yet, else null. */
export function blocker(path, p) {
  const sizeOk = Number(p.setup.width) > 0 && Number(p.setup.length) > 0
  switch (path) {
    case '/project/setup': return null
    case '/project/photos': return p.setup.name.trim() ? null : 'Start by describing the room.'
    case '/project/orientation': return p.photos.length ? null : 'Add at least one photo first.'
    case '/project/furniture': return p.orientation.confirmed ? null : 'Confirm the room orientation first.'
    case '/project/analyze': return p.orientation.confirmed ? null : 'Confirm the room orientation first.'
    case '/project/floorplan': return p.analysis.status === 'done' || p.plan.room ? null : 'Analyze the room first.'
    case '/project/vastu': return p.plan.confirmed ? null : 'Confirm the floor plan first.'
    case '/project/redesign': return p.vastu.status === 'done' ? null : 'Run the Vastu analysis first.'
    case '/project/results': return p.redesign.status === 'done' ? null : 'Generate the redesign first.'
    default: return sizeOk ? null : null
  }
}

/** Index of the first step that is still blocked (how far the user may navigate). */
export function furthestStep(p) {
  for (let i = 0; i < STEPS.length; i++) if (blocker(STEPS[i].path, p)) return i - 1
  return STEPS.length - 1
}
