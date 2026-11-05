/**
 * 图标 SVG 源（移植自 prototype/assets/proto.js 的 sprite）。
 * 小程序不支持内联 SVG；为避免内联 style 携带大段 base64（Taro 性能提示），
 * 这里只是源数据，由 `npm run gen:icons` 生成 src/styles/icons.generated.scss，组件通过 CSS 类引用。
 */

const svg = (vb: string, body: string) => `<svg xmlns="http://www.w3.org/2000/svg" viewBox="${vb}">${body}</svg>`
const stroke = (color: string, width: number) =>
  `fill="none" stroke="${color}" stroke-width="${width}" stroke-linecap="round" stroke-linejoin="round"`

const GREY = '#9AA1A9'

export const ICON_SVGS = {
  coin: svg(
    '0 0 24 24',
    '<circle cx="12" cy="12" r="10" fill="#FFD21F" stroke="#000" stroke-width="2"/><circle cx="12" cy="12" r="6" fill="none" stroke="#000" stroke-width="1.5"/>'
  ),
  xp: svg(
    '0 0 24 24',
    '<path d="M13.5 2 L5 13.5 h6 L9.5 22 L19 10 h-6 Z" fill="#FFD21F" stroke="#000" stroke-width="2" stroke-linejoin="round"/>'
  ),
  doc: svg('0 0 16 16', `<path d="M4 1.5h5l3 3V14.5H4z M9 1.5v3h3" fill="none" stroke="${GREY}" stroke-width="1.6"/>`),
  link: svg(
    '0 0 16 16',
    `<path d="M6.5 9.5l3-3 M7 4.5l1.5-1.5a2.5 2.5 0 013.5 3.5L10.5 8 M9 11.5L7.5 13a2.5 2.5 0 01-3.5-3.5L5.5 8" fill="none" stroke="${GREY}" stroke-width="1.6"/>`
  ),
  video: svg(
    '0 0 16 16',
    `<rect x="1.5" y="3" width="13" height="10" rx="2" fill="none" stroke="${GREY}" stroke-width="1.6"/><path d="M6.5 6v4l3.5-2z" fill="${GREY}"/>`
  ),
  close: svg('0 0 18 18', `<path d="M3 3l12 12M15 3L3 15" ${stroke('#000', 2.5)}/>`),
  back: svg('0 0 12 20', `<path d="M10 2L2 10l8 8" ${stroke('#000', 2.5)}/>`),
  backWhite: svg('0 0 12 20', `<path d="M10 2L2 10l8 8" ${stroke('#fff', 2.5)}/>`),
  warn: svg(
    '0 0 18 18',
    '<circle cx="9" cy="9" r="8" fill="#E5322D"/><path d="M9 4.5v5.5" stroke="#fff" stroke-width="2" stroke-linecap="round"/><circle cx="9" cy="13" r="1.2" fill="#fff"/>'
  ),
  ok: svg(
    '0 0 22 22',
    `<circle cx="11" cy="11" r="10" fill="#14A160"/><path d="M6 11.5l3.2 3.2L16 8" ${stroke('#fff', 2.4)}/>`
  ),
  // 判题标记（.mark）
  markOk: svg('0 0 28 28', `<path d="M4 15 L11 22 L25 5" ${stroke('#14A160', 4.5)}/>`),
  markNo: svg('0 0 28 28', `<path d="M5 5 L23 23 M23 5 L5 23" ${stroke('#E5322D', 4.5)}/>`),
  // “我的”页列表图标（proto.js i-chart / i-tree / i-clock / i-cross-book / i-folder / i-crown）。
  // 本期只有“历史记录”可用，其余入口置灰（同首页“传文档”），所以另备一套灰色
  ...listIcons('', '#000'),
  ...listIcons('Grey', GREY)
}

function listIcons<S extends '' | 'Grey'>(suffix: S, color: string) {
  const st = stroke(color, 2)
  const icon = (body: string) => svg('0 0 24 24', body)
  return {
    [`chart${suffix}`]: icon(`<path ${st} d="M3 21h18 M6 17v-5 M11 17V7 M16 17v-8 M21 17V4"/>`),
    [`tree${suffix}`]: icon(`<path ${st} d="M12 6v14 M12 10H6v4 M12 15h6v4"/><rect ${st} x="9" y="2" width="6" height="4"/>`),
    [`clock${suffix}`]: icon(`<circle ${st} cx="12" cy="12" r="9"/><path ${st} d="M12 7v5l3 2"/>`),
    [`crossBook${suffix}`]: icon(`<path ${st} d="M5 3h14v18H5z M9 9l6 6 M15 9l-6 6"/>`),
    [`folder${suffix}`]: icon(`<path ${st} d="M3 6h6l2 2h10v11H3z"/>`),
    [`crown${suffix}`]: icon(`<path ${st} d="M3 8l4 4 5-7 5 7 4-4-2 11H5z"/>`)
  } as Record<`${'chart' | 'tree' | 'clock' | 'crossBook' | 'folder' | 'crown'}${S}`, string>
}

/**
 * 底部标签栏图标（proto.js tabs）：选中时黑线 + 黄色填充，未选中灰线无填充。
 * 自定义 tabBar 是独立组件，app.wxss 对它不生效，所以单独生成 tab-icons.generated.scss 给它用。
 */
const tab = (on: boolean, body: (c: string, f: string) => string) => svg('0 0 26 26', body(on ? '#000' : '#5E6670', on ? '#FFD21F' : 'none'))
const tabQuest = (c: string, f: string) =>
  `<rect x="3" y="4" width="20" height="18" fill="${f}" stroke="${c}" stroke-width="2.2" stroke-linejoin="round"/><path d="M13 4v18 M3 13h10" fill="none" stroke="${c}" stroke-width="2.2" stroke-linejoin="round"/>`
const tabReview = (c: string, f: string) =>
  `<circle cx="13" cy="13" r="9.5" fill="${f}" stroke="${c}" stroke-width="2.2" stroke-linecap="round"/><path d="M13 8v5l3.5 2.5" fill="none" stroke="${c}" stroke-width="2.2" stroke-linecap="round"/>`
const tabMe = (c: string, f: string) =>
  `<circle cx="13" cy="9" r="4.5" fill="${f}" stroke="${c}" stroke-width="2.2" stroke-linecap="round"/><path d="M4.5 23c1-5 4.5-7 8.5-7s7.5 2 8.5 7" fill="none" stroke="${c}" stroke-width="2.2" stroke-linecap="round"/>`

export const TAB_ICON_SVGS = {
  'tab-quest': tab(false, tabQuest),
  'tab-quest-on': tab(true, tabQuest),
  'tab-review': tab(false, tabReview),
  'tab-review-on': tab(true, tabReview),
  'tab-me': tab(false, tabMe),
  'tab-me-on': tab(true, tabMe)
}

export type IconName = keyof typeof ICON_SVGS
