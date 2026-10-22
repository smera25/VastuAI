// Seed a project at the floor plan stage (no photos needed) to test editor interactions in isolation.
export const seedProject = (over = {}) => ({
  version: 1, id: 'room-seed', createdAt: 0,
  setup: { name: 'Seed room', roomType: 'bedroom', width: '4', length: '3.5', style: 'modern', budgetValue: '' },
  photos: [], orientation: { topEdgeDirection: 'east', heading: null, headingSource: null, confirmed: true, note: null },
  openings: [{ id: 'door-1', type: 'door', wall: 'bottom', offset: 2.6, width: 0.9, is_main_entrance: true, provenance: 'user_provided' }, { id: 'win-1', type: 'window', wall: 'top', offset: 1.2, width: 1.4, provenance: 'user_provided' }],
  furniture: [
    { id: 'bed-1', item: 'bed', label: 'Bed', source: 'user_added', confirmed: true, width: 1.6, length: 2, dimsSource: 'default', x: null, y: null, facingEdge: null, headboardEdge: null },
    { id: 'wardrobe-1', item: 'wardrobe', label: 'Wardrobe', source: 'user_added', confirmed: true, width: 0.6, length: 1.8, dimsSource: 'user', x: null, y: null, facingEdge: null, headboardEdge: null },
  ],
  detection: { status: 'unavailable', candidates: [], error: null, reason: 'x' },
  analysis: { status: 'manual', jobId: null, stages: [], result: null, error: null },
  plan: { room: { width: 4, length: 3.5, dimensionsSource: 'user_provided' }, confirmed: false },
  vastu: { status: 'idle', report: null, error: null },
  prefs: { style: 'modern', paletteId: 'warm-neutrals', budgetValue: '', retain: [], replace: [], add: [], storage: 'moderate', functional: [], accessibility: [], wheelchair: false, notes: '', followVastu: true, referencePhotoId: null, referenceViewEdge: 'top' },
  redesign: { status: 'idle', spec: null, error: null }, visualization: { status: 'idle', jobId: null, stages: [], result: null, error: null },
  ...over,
})
