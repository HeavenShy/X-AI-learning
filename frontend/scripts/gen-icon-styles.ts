/** 生成 src/styles/icons.generated.scss：npm run gen:icons */
import { mkdirSync, writeFileSync } from 'node:fs'
import { dirname, join } from 'node:path'

import { ICON_STYLES_PATH, renderIconScss } from '../src/assets/icon-styles'

const out = join(__dirname, '..', ICON_STYLES_PATH)
mkdirSync(dirname(out), { recursive: true })
writeFileSync(out, renderIconScss())
console.log(`wrote ${ICON_STYLES_PATH}`)
