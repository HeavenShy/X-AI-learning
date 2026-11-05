/**
 * 把图标 / 爆炸框 / 太阳码的 SVG 渲染成 SCSS（background-image: base64 data URI）。
 * 只在生成脚本和单测里使用，不会被小程序运行时引用。
 */

import { burstSvg, sunCodeSvg, svgUri } from '../core/graphics'
import { iconClass } from './icon-class'
import { ICON_SVGS, TAB_ICON_SVGS, type IconName } from './icons'

export { iconClass }

export const ICON_STYLES_PATH = 'src/styles/icons.generated.scss'
export const TAB_ICON_STYLES_PATH = 'src/styles/tab-icons.generated.scss'

/** 类名 → SVG 源 */
export const IMAGE_SVGS: Record<string, string> = {
  ...Object.fromEntries(Object.entries(ICON_SVGS).map(([name, svg]) => [iconClass(name as IconName), svg])),
  // 拟声词爆炸框（proto.js data-burst="16,56,36"）
  'img-burst': burstSvg(16, 56, 36, 120, 100),
  // 海报太阳码占位
  'img-sun-code': sunCodeSvg()
}

function renderScss(svgs: Record<string, string>): string {
  const rules = Object.entries(svgs).map(
    ([cls, svg]) => `.${cls} {\n  background-image: url("${svgUri(svg)}");\n}\n`
  )
  return [
    '/* 自动生成，请勿手改：修改 src/assets/icons.ts 后运行 `npm run gen:icons` */',
    '/* 图标放在 CSS 而不是内联 style，避免每次 setData 传输大段 base64（Taro 性能提示） */',
    '',
    ...rules
  ].join('\n')
}

export const renderIconScss = () => renderScss(IMAGE_SVGS)
export const renderTabIconScss = () => renderScss(TAB_ICON_SVGS)
