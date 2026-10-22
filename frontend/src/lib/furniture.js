// Mirror of backend app/furniture.py (sizes are TYPICAL defaults - estimates, never measurements).
export const CATALOG = {
  bed: { label: 'Bed', width: 1.6, length: 2.0, color: '#c9d6cf', heavy: true },
  single_bed: { label: 'Single bed', width: 1.0, length: 2.0, color: '#c9d6cf', heavy: true },
  nightstand: { label: 'Nightstand', width: 0.45, length: 0.4, color: '#dcd0bb' },
  wardrobe: { label: 'Wardrobe', width: 1.2, length: 0.6, color: '#d9c7a3', heavy: true },
  dresser: { label: 'Dresser', width: 1.0, length: 0.5, color: '#d9c7a3', heavy: true },
  storage: { label: 'Storage unit', width: 0.9, length: 0.45, color: '#d9c7a3', heavy: true },
  bookshelf: { label: 'Bookshelf', width: 0.9, length: 0.35, color: '#d9c7a3', heavy: true },
  desk: { label: 'Desk', width: 1.2, length: 0.6, color: '#e6dcb8' },
  chair: { label: 'Chair', width: 0.5, length: 0.5, color: '#cfe0c3' },
  sofa: { label: 'Sofa', width: 2.0, length: 0.85, color: '#bfd3d6', heavy: true },
  armchair: { label: 'Armchair', width: 0.8, length: 0.8, color: '#bfd3d6' },
  table: { label: 'Table', width: 0.8, length: 0.8, color: '#e3d5b5' },
  coffee_table: { label: 'Coffee table', width: 1.0, length: 0.55, color: '#e3d5b5' },
  dining_table: { label: 'Dining table', width: 1.4, length: 0.9, color: '#e3d5b5' },
  tv_unit: { label: 'TV / TV unit', width: 1.4, length: 0.4, color: '#cfcfca' },
  counter: { label: 'Counter', width: 2.0, length: 0.6, color: '#d4d4cf', heavy: true },
  stove: { label: 'Stove / hob', width: 0.6, length: 0.6, color: '#e4b9a8' },
  refrigerator: { label: 'Refrigerator', width: 0.7, length: 0.7, color: '#cfe3e6', heavy: true },
  sink: { label: 'Sink', width: 0.6, length: 0.6, color: '#cfe3e6' },
  plant: { label: 'Plant', width: 0.4, length: 0.4, color: '#c5dcb4' },
  other: { label: 'Other item', width: 0.6, length: 0.6, color: '#e1ddd3' },
}

export const furnitureTypes = Object.keys(CATALOG)
export const labelFor = (item) => CATALOG[item]?.label ?? String(item).replace(/_/g, ' ')
export const defaultSize = (item) => {
  const c = CATALOG[item] ?? CATALOG.other
  return { width: c.width, length: c.length }
}
export const colorFor = (item) => (CATALOG[item] ?? CATALOG.other).color

export const ROOM_TYPES = [
  { value: 'bedroom', label: 'Bedroom' },
  { value: 'living_room', label: 'Living room' },
  { value: 'kitchen', label: 'Kitchen' },
  { value: 'study_room', label: 'Study room' },
  { value: 'dining_room', label: 'Dining room' },
  { value: 'other', label: 'Other' },
]

export const STYLES = [
  { value: 'modern', label: 'Modern', blurb: 'Clean lines, calm and uncluttered', swatch: ['#f2efe9', '#4a4a48', '#c9b08a', '#a08a58'] },
  { value: 'minimalist', label: 'Minimalist', blurb: 'Sparse, functional, open floor', swatch: ['#f7f6f2', '#d8d6cf', '#b79f7e', '#2b2b2a'] },
  { value: 'scandinavian', label: 'Scandinavian', blurb: 'Bright, cosy, natural wood', swatch: ['#fafaf7', '#e8dcc6', '#9fb095', '#a8a59d'] },
  { value: 'contemporary', label: 'Contemporary', blurb: 'Current, sophisticated, balanced', swatch: ['#d8d2c6', '#3f5b4a', '#6d4c35', '#c3a46a'] },
  { value: 'bohemian', label: 'Bohemian', blurb: 'Layered, warm, plant-rich', swatch: ['#c4724f', '#d8a844', '#2f6a68', '#f3e9d7'] },
  { value: 'traditional', label: 'Traditional', blurb: 'Classic teak, brass and warmth', swatch: ['#f3ede0', '#7a2e2e', '#6a4a2f', '#b89650'] },
]

export const PALETTES = [
  { id: 'warm-neutrals', label: 'Warm neutrals', colors: ['warm white', 'sand', 'oak', 'soft taupe'], swatch: ['#f3ede2', '#d9c7a3', '#b58e5c', '#9b8a7a'] },
  { id: 'sage-and-stone', label: 'Sage & stone', colors: ['sage green', 'stone grey', 'ivory', 'natural wood'], swatch: ['#9fb095', '#b3b0a7', '#f6f3ea', '#b58e5c'] },
  { id: 'earth-tones', label: 'Earth tones', colors: ['terracotta', 'clay', 'olive', 'cream'], swatch: ['#c4724f', '#a8693f', '#6f7a4c', '#f3e9d7'] },
  { id: 'monochrome', label: 'Soft monochrome', colors: ['off-white', 'light grey', 'charcoal', 'black accents'], swatch: ['#f4f2ee', '#d6d4cf', '#4a4a48', '#1f1f1e'] },
  { id: 'coastal', label: 'Coastal calm', colors: ['white', 'pale blue', 'sand', 'driftwood'], swatch: ['#fbfbf8', '#b9d0d6', '#e4d6b8', '#a39581'] },
]

export const BUDGETS = [
  { value: '', label: 'Not specified', inr: null },
  { value: 'under-50k', label: 'Under ₹50,000', inr: 50000 },
  { value: '50k-1.5l', label: '₹50,000 – ₹1,50,000', inr: 150000 },
  { value: '1.5l-4l', label: '₹1,50,000 – ₹4,00,000', inr: 400000 },
  { value: 'above-4l', label: 'Above ₹4,00,000', inr: 1000000 },
]

export const FUNCTION_OPTIONS = [
  'Work-from-home desk', 'Extra seating for guests', 'Maximise storage', 'Reading corner', 'Prayer / meditation corner', 'Space for kids to play',
]
export const ACCESS_OPTIONS = ['Step-free / wheelchair clearance', 'Wide walkways', 'Low furniture heights', 'Avoid sharp corners']

export const formatInr = (n) => '₹' + Math.round(n).toLocaleString('en-IN')
