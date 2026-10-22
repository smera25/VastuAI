import chromium from '@sparticuz/chromium'
import puppeteer from 'puppeteer-core'
export async function launch() {
  const path = await chromium.executablePath()
  return puppeteer.launch({ executablePath: path, args: [...chromium.args, '--no-sandbox', '--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream'], headless: 'shell', defaultViewport: { width: 1280, height: 900 } })
}
