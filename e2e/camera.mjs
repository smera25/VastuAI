import { launch } from './launch.mjs'; import { seedProject } from './seed.mjs'
const b = await launch()
const mk = async (denied) => {
  const p = await b.newPage(); const errs = []; p.on('pageerror', e => errs.push(e.message))
  await p.evaluateOnNewDocument((j) => { localStorage.setItem('vastu-atelier:project:v1', j) }, JSON.stringify(seedProject({ photos: [] })))
  if (denied) await p.evaluateOnNewDocument(() => { navigator.mediaDevices.getUserMedia = () => Promise.reject(Object.assign(new Error('denied'), { name: 'NotAllowedError' })) })
  await p.goto('http://localhost:5173/project/photos', { waitUntil: 'networkidle0' }); return { p, errs }
}
const click = (p, t) => p.evaluate((t) => [...document.querySelectorAll('button')].find(b => b.textContent.trim().includes(t) && !b.disabled).click(), t)
{ // live camera (Chrome fake device)
  const { p, errs } = await mk(false); await click(p, 'Use camera')
  await p.waitForFunction(() => document.querySelector('.camera video')?.videoWidth > 0, { timeout: 15000 })
  console.log('camera live, video', await p.$eval('.camera video', v => `${v.videoWidth}x${v.videoHeight}`), '| hint:', await p.$eval('.camera-hint', e => e.textContent.slice(0, 60)))
  await click(p, 'Capture photo'); await new Promise(r => setTimeout(r, 400)); await click(p, 'Capture photo'); await new Promise(r => setTimeout(r, 400))
  await p.screenshot({ path: 'shots/13-camera.png' })
  await click(p, 'Done'); await p.waitForFunction(() => document.querySelectorAll('.photo-grid img').length === 2)
  const dims = await p.$$eval('.photo-grid img', i => i.map(x => x.complete && x.naturalWidth > 0))
  console.log('captured photos rendered:', dims, '| continue enabled:', !(await p.$eval('.step-footer .btn.sage', e => e.disabled)), '| errors:', errs)
}
{ // permission denied
  const { p } = await mk(true); await click(p, 'Use camera'); await p.waitForSelector('.camera .alert')
  console.log('denied ->', (await p.$eval('.camera .alert', e => e.textContent)).slice(0, 140))
  await p.screenshot({ path: 'shots/14-camera-denied.png' })
}
await b.close()
