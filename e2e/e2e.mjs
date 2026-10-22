import { launch } from './launch.mjs'
import { fileURLToPath } from 'node:url'
const R = fileURLToPath(new URL('../', import.meta.url))
const MOBILE = !!process.env.MOBILE
const b = await launch(); const p = await b.newPage()
if (MOBILE) await p.setViewport({ width: 390, height: 844, deviceScaleFactor: 2, isMobile: true, hasTouch: true })
const SH = MOBILE ? 'm-' : ''
const problems = []
p.on('pageerror', e => problems.push('PAGEERROR ' + e.message))
p.on('console', m => { if (m.type() === 'error' && !/fonts\.g|net::ERR_(NAME|INTERNET|CONNECTION)|Failed to load resource/.test(m.text())) problems.push('CONSOLE ' + m.text()) })
p.on('response', r => { if (r.status() >= 500) problems.push(`HTTP ${r.status()} ${r.url()}`) })
const log = (...a) => console.log(...a)
const sleep = (ms) => new Promise(r => setTimeout(r, ms))
const btn = async (text) => { const h = await p.evaluateHandle((t) => [...document.querySelectorAll('button,a.btn')].find(e => e.textContent.trim().includes(t) && !e.disabled), text); const el = h.asElement(); if (!el) throw new Error('no enabled button: ' + text); await el.evaluate(e => { e.scrollIntoView({ block: 'center' }); e.click() }) }
const shot = (n) => p.screenshot({ path: `shots/${SH}${n}.png` })
const edgeLabels = () => p.$$eval('svg.floorplan [data-edge]', (g) => { const m = Object.fromEntries(g.slice(0, 4).map(x => [x.getAttribute('data-edge'), x.querySelector('text').textContent])); return { top: m.top, right: m.right, bottom: m.bottom, left: m.left } })
const step = async (name, fn) => { try { await fn(); const ov = await p.evaluate(() => { const w = document.documentElement.clientWidth; return { over: document.documentElement.scrollWidth - w, offenders: [...document.querySelectorAll('body *')].filter(e => e.getBoundingClientRect().right > w + 2 && !e.closest('.stepper') && !e.closest('svg')).slice(0, 3).map(e => e.className?.toString().slice(0, 40) || e.tagName) } }); log('✓', name, MOBILE && ov.over > 1 ? `  ⚠ horizontal overflow ${ov.over}px: ${ov.offenders.join(', ')}` : '') } catch (e) { log('✗', name, '->', e.message); await shot('FAIL-' + name.replace(/\W+/g, '_')); throw e } }

await p.goto('http://localhost:5173/', { waitUntil: 'networkidle0' })
await step('1 setup', async () => {
  await btn('Start New Room Analysis'); await p.waitForSelector('#name')
  // Guard: cannot skip ahead
  await p.type('#name', 'Master bedroom'); await p.type('#w', '4'); await p.type('#l', '3.5')
  await p.click('[role=radio][aria-checked=false].style-card'); await btn('Continue to photos'); await p.waitForSelector('input[aria-label="Upload photos"]')
})
await step('2 photos: validation + upload', async () => {
  const input = await p.$('input[aria-label="Upload photos"]')
  await input.uploadFile(R + 'response.json')   // not an image -> must be rejected client side
  await p.waitForSelector('.alert.warn'); const warn = await p.$eval('.alert.warn', e => e.textContent); if (!/not a JPG, PNG or WEBP/.test(warn)) throw new Error('bad-file warning missing: ' + warn)
  const next = await p.$eval('.step-footer .btn.sage', e => e.disabled); if (!next) throw new Error('Continue should be disabled with 0 photos')
  await input.uploadFile(R + 'myroom1.jpeg', R + 'myroom2.jpeg', R + 'myroom3.jpeg')
  await p.waitForFunction(() => document.querySelectorAll('.photo-grid img').length === 3, { timeout: 20000 })
  await shot('03-photos'); await btn('Continue to orientation'); await p.waitForSelector('[role=radiogroup][aria-label^="Compass"]')
})
await step('3 orientation', async () => {
  if (!(await p.$eval('.step-footer .btn.sage', e => e.disabled))) throw new Error('Continue must be disabled until orientation confirmed')
  await p.click('[role=radio][aria-label="East"]')
  const l = await edgeLabels(); if (JSON.stringify(l) !== JSON.stringify({ top: 'EAST', right: 'SOUTH', bottom: 'WEST', left: 'NORTH' })) throw new Error('preview labels wrong: ' + JSON.stringify(l))
  await btn('Add door'); await btn('Add window')
  await p.$$eval('.opening-row', rows => rows.length === 2 || (() => { throw new Error('openings not added') })())
  const boxes = await p.$$('.opening-row input[type=checkbox]'); await boxes[0].click()
  await shot('04-orientation')
  await p.click('.confirm-card input'); await btn('Continue to furniture')
  await p.waitForSelector('.f-list, .empty, .alert')
})
await step('4 furniture (detection honestly unavailable)', async () => {
  await p.waitForFunction(() => /isn’t available on this server|No common furniture|Detection failed/.test(document.body.textContent), { timeout: 30000 })
  const txt = await p.$eval('.alert', e => e.textContent); log('   detection alert:', txt.slice(0, 110))
  await p.select('select[aria-label="Item to add"]', 'bed'); await btn('Add item')
  await p.select('select[aria-label="Item to add"]', 'wardrobe'); await btn('Add item')
  await p.select('select[aria-label="Item to add"]', 'desk'); await btn('Add item')
  await shot('05-furniture'); await btn('Continue to analysis'); await p.waitForSelector('[aria-label="What this server can do"]')
})
await step('5 analyze (real job, real stages)', async () => {
  await shot('06-analyze-before'); await btn('Analyze Room')
  await p.waitForFunction(() => location.pathname.endsWith('/floorplan'), { timeout: 60000 })
  log('   (redirected to floor plan after the backend job succeeded)')
})
await step('6 floor plan: unplaced items are NOT invented', async () => {
  await p.waitForSelector('svg.floorplan')
  const t = await p.$eval('.panel', e => e.textContent); if (!/3 items need a position/.test(t)) throw new Error('expected 3 unplaced items, got: ' + t.slice(0, 200))
  const placedCount = await p.$$eval('svg.floorplan [data-furniture]', g => g.length); if (placedCount !== 0) throw new Error('furniture was invented')
  if (!(await p.$eval('.step-footer .btn.sage', e => e.disabled))) throw new Error('Confirm must be blocked while items unplaced')
  const alertTxt = await p.$$eval('.alert', a => a.map(x => x.textContent).join(' | ')); log('   alerts:', alertTxt.slice(0, 230))
})
await step('6b place + edit furniture (numeric + drag + keyboard)', async () => {
  for (let i = 0; i < 3; i++) await btn('Place on plan')
  await p.waitForSelector('svg.floorplan [data-furniture]')
  const ids = await p.$$eval('svg.floorplan [data-furniture]', g => g.map(x => x.getAttribute('data-furniture')))
  if (ids.length !== 3) throw new Error('expected 3 placed, got ' + ids.length)
  const setNum = async (label, v) => { const i = await p.$(`input[aria-label="${label}"]`); await i.evaluate(e => { e.focus(); e.select() }); await p.keyboard.type(String(v)); await sleep(60) }
  const sel = async (kind) => { const h = await p.evaluateHandle((k) => [...document.querySelectorAll('.mini-list button')].find(b => b.textContent.trim().toLowerCase().startsWith(k)), kind); await h.evaluate(el => el.click()) }
  await sel('bed'); await setNum('x position in metres', 0.5); await setNum('y position in metres', 0.5)
  const rv = (l) => p.$eval(`input[aria-label="${l}"]`, e => e.value)
  if ((await rv('x position in metres')) !== '0.5' || (await rv('y position in metres')) !== '0.5') throw new Error('decimal typing broken: ' + await rv('x position in metres') + ',' + await rv('y position in metres'))
  await p.select('.inspector select', 'left')   // headboard against the left wall
  await sel('wardrobe'); await setNum('width in metres', 0.6); await setNum('length in metres', 1.8); await setNum('x position in metres', 3.0); await setNum('y position in metres', 0.5)
  if ((await rv('width in metres')) !== '0.6' || (await rv('x position in metres')) !== '3') throw new Error('wardrobe edit wrong')
  // keyboard move
  const g = await p.$('svg.floorplan [data-furniture^="wardrobe"]'); await g.evaluate(el => el.focus())
  const before = await p.$eval('input[aria-label="y position in metres"]', e => +e.value); await sleep(400); log('   state:', await p.evaluate(() => JSON.stringify(JSON.parse(localStorage.getItem('vastu-atelier:project:v1')).furniture.map(f => [f.id.slice(0,8), f.label, f.x, f.y, f.width, f.length])))); log('   active before keys:', await p.evaluate(() => document.activeElement.getAttribute('data-furniture') || document.activeElement.tagName), '| inspector:', await p.$eval('.inspector h4', e => e.textContent)); await p.keyboard.press('ArrowUp'); await p.keyboard.press('ArrowUp'); await sleep(100)
  const after = await p.$eval('input[aria-label="y position in metres"]', e => +e.value); if (!(after > before)) throw new Error(`arrow keys did not move: ${before} -> ${after}`)
  // drag desk with mouse
  const desk = await p.$('svg.floorplan [data-furniture^="desk"] rect:last-of-type'); const bb = await desk.boundingBox()
  await p.mouse.move(bb.x + bb.width / 2, bb.y + bb.height / 2); await p.mouse.down(); await p.mouse.move(bb.x + bb.width / 2 - 120, bb.y + bb.height / 2 - 90, { steps: 8 }); await p.mouse.up()
  await sel('desk'); const dx = await p.$eval('input[aria-label="x position in metres"]', e => +e.value); log('   desk x after drag:', dx)
  await p.select('.inspector select', 'top').catch(() => {})
  await shot('07-floorplan-edit')
})
await step('6c Correct Directions relabels everything', async () => {
  await btn('Correct Directions')
  const click = async (d) => { await btn(d); await sleep(150) }
  const exp = { North: { top: 'NORTH', right: 'EAST', bottom: 'SOUTH', left: 'WEST' }, East: { top: 'EAST', right: 'SOUTH', bottom: 'WEST', left: 'NORTH' }, South: { top: 'SOUTH', right: 'WEST', bottom: 'NORTH', left: 'EAST' }, West: { top: 'WEST', right: 'NORTH', bottom: 'EAST', left: 'SOUTH' } }
  for (const d of ['North', 'South', 'West', 'East']) {
    await p.evaluate((t) => [...document.querySelectorAll('.panel .seg button')].find(x => x.textContent.trim() === t).click(), d); await sleep(150)
    const got = await edgeLabels(); if (JSON.stringify(got) !== JSON.stringify(exp[d])) throw new Error(`top=${d}: ${JSON.stringify(got)}`)
    const arrow = await p.$eval('[data-role=north-arrow]', e => +e.getAttribute('data-rotation')); const want = { North: 0, East: 270, South: 180, West: 90 }[d]; if (arrow !== want) throw new Error(`arrow ${arrow} != ${want} for ${d}`)
  }
  log('   all four orientations verified in the live UI (labels + north arrow)')
  await shot('08-floorplan-east')
})
await step('6d confirm floor plan', async () => { await btn('Confirm Floor Plan'); await p.waitForFunction(() => location.pathname.endsWith('/vastu')) })
await step('7 vastu report', async () => {
  await p.waitForSelector('.finding', { timeout: 20000 })
  const n = await p.$$eval('.finding', f => f.length); const txt = await p.$eval('.stats', e => e.textContent); log('   findings:', n, '|', txt.replace(/\s+/g, ' '))
  await shot('09-vastu')
})
await step('8 redesign preferences -> plan + honest viz error', async () => {
  await btn('Continue to redesign'); await p.waitForSelector('.palette')
  await p.click('.palette:nth-child(2)'); await p.select('select[aria-label="Furniture to add"]', 'nightstand'); await btn('Add')
  await shot('10-redesign-form'); await btn('Generate redesign')
  await p.waitForFunction(() => /Image generation isn’t configured|couldn’t be generated|Your redesign is ready/.test(document.body.textContent), { timeout: 60000 })
  const t = await p.$eval('.alert.warn, .alert.danger', e => e.textContent); log('   viz alert:', t.slice(0, 160))
  await shot('11-redesign-done'); await btn('View results'); await p.waitForSelector('.results')
})
await step('9 results page', async () => {
  await p.waitForSelector('.plans svg.floorplan')
  await p.evaluate(() => [...document.querySelectorAll('.seg button')].find(x => x.textContent === 'Compare').click()); await sleep(300)
  const cnt = await p.$$eval('svg.floorplan', s => s.length); log('   floor plans on page (compare):', cnt)
  const w = await p.$eval('.alert.warn', e => e.textContent); log('   warnings:', w.replace(/\s+/g, ' ').slice(0, 200))
  await p.screenshot({ path: `shots/${SH}12-results.png`, fullPage: true })
})
await step('persistence across reload', async () => {
  await p.reload({ waitUntil: 'networkidle0' }); await p.waitForSelector('.results'); const imgs = await p.$$eval('.photo-grid img', i => i.length); if (imgs !== 3) throw new Error('photos lost on reload: ' + imgs)
})
console.log('\nproblems:', problems.length ? problems : 'none')
await b.close()
