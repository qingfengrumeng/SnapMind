// Run against desktop dev started with WebView2 remote debugging on port 9223.
// Measures pixels ready, checks canvas export, and cancels without saving or AI calls.
import { chromium } from 'playwright'
import assert from 'node:assert/strict'

const browser = await chromium.connectOverCDP('http://127.0.0.1:9223')
const pages = browser.contexts()[0].pages()
const main = pages.find(p => p.url().includes('5174') && !p.url().includes('desktop='))
const capture = pages.find(p => p.url().includes('desktop=capture'))
assert.ok(main && capture, 'Start SnapMind desktop dev with remote debugging first')
const invoke = command => main.evaluate(command => window.__TAURI_INTERNALS__.invoke(command), command)
const errors = []
capture.on('pageerror', e => errors.push(e.message))
const timings = []
try {
  for (let i = 0; i < 5; i++) {
    const originalWindows = (await invoke('native_status')).windows
    const start = Date.now()
    await invoke('begin_capture')
    const nativeMs = Date.now() - start
    const frameId = (await invoke('get_desktop_state')).frame.asset.id
    await capture.waitForFunction(id => { const root = document.querySelector('.capture-overlay'); return root?.dataset.ready === 'true' && root.dataset.sourceId === id }, frameId, { timeout: 10000 })
    for (let n = 0; n < 50 && !(await invoke('native_status')).windows.capture.visible; n++) await capture.waitForTimeout(20)
    const result = await capture.evaluate(async () => {
      const mark = performance.getEntriesByName('snapmind-capture-ready').at(-1)
      const drawnAt = performance.timeOrigin + mark.startTime
      const canvas = document.querySelector('.capture-screen')
      const bounds = canvas.getBoundingClientRect()
      const aligned = Math.abs(bounds.x) < 1 && Math.abs(bounds.y) < 1
        && Math.abs(bounds.width - innerWidth) < 1 && Math.abs(bounds.height - innerHeight) < 1
        && Math.abs(canvas.width - innerWidth * devicePixelRatio) < 2
        && Math.abs(canvas.height - innerHeight * devicePixelRatio) < 2
      const opaque = canvas.getContext('2d').getImageData(0, 0, 1, 1).data[3] === 255
      const crop = document.createElement('canvas')
      crop.width = 120; crop.height = 80
      crop.getContext('2d').drawImage(canvas, 100, 100, 120, 80, 0, 0, 120, 80)
      const image = new Image()
      image.src = crop.toDataURL('image/png')
      await image.decode()
      return { drawnAt, opaque, aligned, cropWidth: image.width, cropHeight: image.height }
    })
    assert.equal(result.opaque, true)
    assert.equal(result.aligned, true, 'Captured pixels must align with the physical desktop')
    const duringCapture = await invoke('native_status')
    assert.equal(duringCapture.windows.capture.visible, true, 'Ready frame must be shown')
    for (const label of ['main', 'image', 'workspace']) assert.deepEqual(duringCapture.windows[label], originalWindows[label], `${label} must remain in place during capture`)
    assert.deepEqual([result.cropWidth, result.cropHeight], [120, 80])
    timings.push({ nativeMs, pixelsReadyMs: Math.round(result.drawnAt - start) })
    await capture.getByRole('button', { name: /Esc/ }).evaluate(e => e.click())
    assert.equal((await invoke('get_desktop_state')).captureActive, false)
    const afterCancel = await invoke('native_status')
    assert.equal(afterCancel.windows.capture.visible, false)
    for (const label of ['main', 'image', 'workspace']) assert.deepEqual(afterCancel.windows[label], originalWindows[label], `${label} must remain in place after cancellation`)
    await capture.waitForTimeout(180)
  }
  assert.deepEqual(errors, [])
  console.log(JSON.stringify({ timings, pixelAlignment: 'PASS', originalWindowsUnchanged: 'PASS', canvasExport: 'PASS', cancel: 'PASS', pageErrors: errors }))
} finally {
  await invoke('cancel_capture').catch(() => {})
  await browser.close()
}
