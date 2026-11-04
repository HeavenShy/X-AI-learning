/**
 * 图形工具：小程序不支持内联 SVG，图标/爆炸框等用 SVG data URI 做背景；
 * 太阳码点阵同时供页面预览（SVG）和海报 Canvas 使用。算法移植自 prototype/assets/proto.js。
 */

const B64 = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/'

/** 只处理 ASCII 的 base64（小程序没有 btoa） */
export function base64Ascii(input: string): string {
  let out = ''
  for (let i = 0; i < input.length; i += 3) {
    const a = input.charCodeAt(i)
    const b = i + 1 < input.length ? input.charCodeAt(i + 1) : NaN
    const c = i + 2 < input.length ? input.charCodeAt(i + 2) : NaN
    const n = (a << 16) | ((b || 0) << 8) | (c || 0)
    out += B64[(n >> 18) & 63] + B64[(n >> 12) & 63]
    out += Number.isNaN(b) ? '=' : B64[(n >> 6) & 63]
    out += Number.isNaN(c) ? '=' : B64[n & 63]
  }
  return out
}

export function svgUri(svg: string): string {
  if (/[^\x00-\x7f]/.test(svg)) throw new Error('svgUri only supports ASCII SVG')
  return `data:image/svg+xml;base64,${base64Ascii(svg)}`
}

/** 拟声词爆炸框多边形顶点（proto.js data-burst） */
export function burstPoints(n: number, R: number, r: number, w: number, h: number): [number, number][] {
  const cx = w / 2
  const cy = h / 2
  const pts: [number, number][] = []
  for (let i = 0; i < n * 2; i++) {
    const rad = (i % 2 ? r : R) * (i % 4 === 0 ? 1 : 0.9)
    const a = (Math.PI * i) / n - Math.PI / 2
    pts.push([+(cx + rad * Math.cos(a) * 1.05).toFixed(1), +(cy + rad * Math.sin(a) * 0.85).toFixed(1)])
  }
  return pts
}

export function burstSvg(n: number, R: number, r: number, w: number, h: number, fill = '#FFF4C4'): string {
  const pts = burstPoints(n, R, r, w, h)
    .map(([x, y]) => `${x},${y}`)
    .join(' ')
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${w} ${h}"><polygon points="${pts}" fill="${fill}" stroke="#000" stroke-width="2.5" stroke-linejoin="round"/></svg>`
}

export interface Dot {
  x: number
  y: number
}

/** 太阳码占位点阵，坐标系 100×100（proto.js data-qr） */
export function sunCodeDots(): Dot[] {
  let seed = 7
  const rnd = () => {
    seed = (seed * 9301 + 49297) % 233280
    return seed / 233280
  }
  const dots: Dot[] = []
  for (let ring = 0; ring < 5; ring++) {
    const rr = 20 + ring * 6
    const count = 18 + ring * 6
    for (let k = 0; k < count; k++) {
      if (rnd() < 0.38) continue
      const a = (2 * Math.PI * k) / count
      dots.push({ x: +(50 + rr * Math.cos(a)).toFixed(1), y: +(50 + rr * Math.sin(a)).toFixed(1) })
    }
  }
  return dots
}

export const SUN_CODE_EYES: [number, number][] = [
  [22, 22],
  [78, 22],
  [22, 78]
]

/** 太阳码预览 SVG（中心的“懂”字是非 ASCII，用页面文字叠加） */
export function sunCodeSvg(): string {
  let out = '<circle cx="50" cy="50" r="48" fill="#fff"/>'
  for (const d of sunCodeDots()) out += `<circle cx="${d.x}" cy="${d.y}" r="2.1" fill="#000"/>`
  for (const [x, y] of SUN_CODE_EYES) {
    out += `<circle cx="${x}" cy="${y}" r="8" fill="#fff" stroke="#000" stroke-width="3"/><circle cx="${x}" cy="${y}" r="3.2" fill="#000"/>`
  }
  out += '<circle cx="50" cy="50" r="13" fill="#FFD21F" stroke="#000" stroke-width="2.5"/>'
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">${out}</svg>`
}
