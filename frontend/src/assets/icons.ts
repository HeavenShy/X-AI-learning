/** 图标（移植自 prototype/assets/proto.js 的 sprite）。小程序不支持内联 SVG，统一转成 data URI 作背景。 */

import { svgUri } from '../core/graphics'

const svg = (vb: string, body: string) => `<svg xmlns="http://www.w3.org/2000/svg" viewBox="${vb}">${body}</svg>`
const stroke = (color: string, width: number) =>
  `fill="none" stroke="${color}" stroke-width="${width}" stroke-linecap="round" stroke-linejoin="round"`

const GREY = '#9AA1A9'

const RAW = {
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
  markNo: svg('0 0 28 28', `<path d="M5 5 L23 23 M23 5 L5 23" ${stroke('#E5322D', 4.5)}/>`)
}

export type IconName = keyof typeof RAW

const cache: Partial<Record<IconName, string>> = {}

export function iconUri(name: IconName): string {
  if (!cache[name]) cache[name] = svgUri(RAW[name])
  return cache[name] as string
}
