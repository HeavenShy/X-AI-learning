/**
 * 图标改为 CSS 类（Taro 提示：内联 style 的 base64 数据量过大会影响渲染性能）。
 * 生成的 SCSS 必须与 SVG 源保持一致：改了图标请运行 `npm run gen:icons`。
 */
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'

import { ICON_SVGS } from '../src/assets/icons'
import {
  ICON_STYLES_PATH,
  iconClass,
  IMAGE_SVGS,
  renderIconScss,
  renderTabIconScss,
  TAB_ICON_STYLES_PATH
} from '../src/assets/icon-styles'
import { TAB_ICON_SVGS } from '../src/assets/icons'

const decode = (b64: string) => Buffer.from(b64, 'base64').toString('ascii')

test('每个图标都有对应的 CSS 类', () => {
  const scss = renderIconScss()
  for (const name of Object.keys(ICON_SVGS)) {
    assert.ok(scss.includes(`.${iconClass(name as keyof typeof ICON_SVGS)} {`), `缺少 ${name}`)
  }
  assert.ok(scss.includes('.img-burst {'))
  assert.ok(scss.includes('.img-sun-code {'))
})

test('类名为 kebab-case', () => {
  assert.equal(iconClass('markOk'), 'icon-mark-ok')
  assert.equal(iconClass('backWhite'), 'icon-back-white')
  assert.equal(iconClass('coin'), 'icon-coin')
})

test('data URI 解码后与 SVG 源一致', () => {
  const scss = renderIconScss()
  for (const [cls, svg] of Object.entries(IMAGE_SVGS)) {
    const m = scss.match(new RegExp(`\\.${cls} \\{\\s*background-image: url\\("data:image/svg\\+xml;base64,([A-Za-z0-9+/=]+)"\\)`))
    assert.ok(m, `${cls} 规则格式不对`)
    assert.equal(decode(m[1]), svg)
  }
})

test('提交的生成文件是最新的（否则运行 npm run gen:icons）', () => {
  const committed = readFileSync(join(__dirname, '..', ICON_STYLES_PATH), 'utf8').replace(/\r\n/g, '\n')
  assert.equal(committed, renderIconScss())
})

test('标签栏图标单独生成，且提交的文件是最新的', () => {
  const scss = renderTabIconScss()
  for (const cls of Object.keys(TAB_ICON_SVGS)) assert.ok(scss.includes(`.${cls} {`), `缺少 ${cls}`)
  const committed = readFileSync(join(__dirname, '..', TAB_ICON_STYLES_PATH), 'utf8').replace(/\r\n/g, '\n')
  assert.equal(committed, scss)
})

test('“我的”列表图标有黑、灰两套', () => {
  assert.ok(renderIconScss().includes('.icon-cross-book {'))
  assert.ok(renderIconScss().includes('.icon-cross-book-grey {'))
})
