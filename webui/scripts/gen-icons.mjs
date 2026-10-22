// 从源码里收集用到的 lucide 图标，生成内置图标集（离线可用，避免依赖 Iconify 在线 API）。
// 用法：npm run icons（改动图标后重新生成并提交 src/icons.generated.ts）
import fs from 'node:fs'
import path from 'node:path'

const root = path.resolve(import.meta.dirname, '..')
const iconJsonPath = path.join(root, 'node_modules', '@iconify-json', 'lucide', 'icons.json')
const all = JSON.parse(fs.readFileSync(iconJsonPath, 'utf-8'))

const used = new Set()
function scan(dir) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, entry.name)
    if (entry.isDirectory()) scan(p)
    else if (/\.(vue|ts|tsx)$/.test(entry.name)) {
      const text = fs.readFileSync(p, 'utf-8')
      for (const m of text.matchAll(/lucide:([a-z0-9-]+)/g)) used.add(m[1])
    }
  }
}
scan(path.join(root, 'src'))

function resolveIcon(name, depth = 0) {
  const direct = all.icons?.[name]
  if (direct) return direct
  const alias = all.aliases?.[name]
  if (alias && depth < 5) {
    const parent = resolveIcon(alias.parent, depth + 1)
    if (parent) {
      const merged = { ...parent }
      for (const k of ['rotate', 'hFlip', 'vFlip']) {
        if (alias[k] !== undefined) merged[k] = alias[k]
      }
      return merged
    }
  }
  return null
}

const icons = {}
const missing = []
for (const name of [...used].sort()) {
  const data = resolveIcon(name)
  if (!data) {
    missing.push(name)
    continue
  }
  icons[name] = data
}

const out = `// 本文件由 scripts/gen-icons.mjs 自动生成，请勿手改。
// 内置 ${Object.keys(icons).length} 个 lucide 图标，使控制台在离线环境也能显示图标。
import { addCollection } from '@iconify/vue'
import type { IconifyJSON } from '@iconify/types'

const collection = ${JSON.stringify(
  { prefix: 'lucide', icons, width: 24, height: 24 },
  null,
  0,
)} as IconifyJSON

addCollection(collection)
`

fs.writeFileSync(path.join(root, 'src', 'icons.generated.ts'), out, 'utf-8')
console.log(`icons: ${Object.keys(icons).length} generated`)
if (missing.length) {
  console.warn('missing icons:', missing.join(', '))
  process.exitCode = 1
}
