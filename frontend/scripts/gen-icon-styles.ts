/** 生成 src/styles/icons.generated.scss 与 tab-icons.generated.scss：npm run gen:icons */
import { mkdirSync, writeFileSync } from 'node:fs'
import { dirname, join } from 'node:path'

import { ICON_STYLES_PATH, renderIconScss, renderTabIconScss, TAB_ICON_STYLES_PATH } from '../src/assets/icon-styles'

for (const [path, render] of [
  [ICON_STYLES_PATH, renderIconScss],
  [TAB_ICON_STYLES_PATH, renderTabIconScss]
] as const) {
  const out = join(__dirname, '..', path)
  mkdirSync(dirname(out), { recursive: true })
  writeFileSync(out, render())
  console.log(`wrote ${path}`)
}
