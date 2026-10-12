// Refresh the local, unicode-split fonts used by the SnapMind interface.
// Google Fonts provides OFL fonts; every font family retains its license below.
import { mkdir, writeFile, readFile } from 'node:fs/promises'
import { resolve } from 'node:path'

const directory = resolve('frontend/public/fonts')
const stylesheet = 'https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400..700&family=Noto+Sans+SC:wght@400..700&family=Noto+Serif+SC:wght@500..700&family=JetBrains+Mono:wght@400..500&display=swap'
const headers = { 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36' }
async function get(url) {
  for (let attempt = 0; attempt < 5; attempt++) {
    try {
      const response = await fetch(url, { headers, signal: AbortSignal.timeout(30000) })
      if (!response.ok) throw new Error(`${response.status}: ${url}`)
      return response
    } catch (error) { if (attempt === 4) throw error; await new Promise(resolve=>setTimeout(resolve,500*(attempt+1))) }
  }
}
await mkdir(directory, { recursive: true })
let css = await (await get(stylesheet)).text()
const assets = [], counters = new Map()
for (const block of css.matchAll(/@font-face\s*\{[^}]+\}/g)) {
  const family = block[0].match(/font-family:\s*'([^']+)'/)[1]
  const url = block[0].match(/url\((https:[^)]+)\)/)[1]
  const name = family.toLowerCase().replaceAll(' ', '-')
  const index = counters.get(name) || 0
  counters.set(name, index + 1)
  const file = `${name}-${index}.woff2`
  assets.push({ url, file })
  css = css.replace(url, `/fonts/${file}`)
}
let cursor = 0, bytes = 0, completed = 0
await Promise.all(Array.from({ length: 6 }, async () => {
  while (cursor < assets.length) {
    const { url, file } = assets[cursor++]
    const cached=process.argv.includes('--refresh')?null:await readFile(resolve(directory,file)).catch(()=>null)
    const data = cached || Buffer.from(await (await get(url)).arrayBuffer())
    if(data.toString('ascii',0,4)!=='wOF2')throw new Error(`Invalid font: ${file}`)
    await writeFile(resolve(directory, file), data)
    bytes += data.length
    if (++completed % 40 === 0) console.log(`Fonts: ${completed}/${assets.length}`)
  }
}))
for (const family of ['spacegrotesk', 'notosanssc', 'notoserifsc', 'jetbrainsmono']) {
  const license = await (await get(`https://raw.githubusercontent.com/google/fonts/main/ofl/${family}/OFL.txt`)).text()
  await writeFile(resolve(directory, `${family}-OFL.txt`), license)
}
await writeFile(resolve(directory, 'fonts.css'), `/* Local fonts. Source: Google Fonts; see the accompanying OFL licenses. */\n${css}`)
console.log(`Saved ${assets.length} font subsets, ${(bytes / 1024 / 1024).toFixed(2)} MB. Browser loads only the subsets needed by the displayed text.`)
