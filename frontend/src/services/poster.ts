/**
 * 分享海报 Canvas 2D 绘制：按原型第 17 屏 .poster 的版式（逻辑宽 323px）逐项绘制。
 * 字体用 wx.loadFontFace 加载的漫画字体（scopes 含 native，Canvas 2D 可用）。
 */

import { SUN_CODE_EYES, sunCodeDots } from '../core/graphics'
import { wrapLines } from '../core/text'
import { DISPLAY_FONT } from './font'

export interface PosterData {
  episode: number
  title: string
  quote: string
  correct: number
  total: number
  duration: string
}

export const POSTER_W = 323
export const POSTER_H = 484

const INK = '#000000'
const MUTED = '#5E6670'
const YELLOW = '#FFD21F'
const LINE = '#B9BFC6'
const BODY = '"PingFang SC", "Microsoft YaHei", sans-serif'
const display = (size: number) => `${size}px "${DISPLAY_FONT}", "PingFang SC", sans-serif`
const body = (size: number) => `${size}px ${BODY}`

type Ctx = CanvasRenderingContext2D

function strokeRect(ctx: Ctx, x: number, y: number, w: number, h: number, width: number, color = INK) {
  ctx.lineWidth = width
  ctx.strokeStyle = color
  ctx.strokeRect(x + width / 2, y + width / 2, w - width, h - width)
}

/** 半色调网点：radial-gradient(circle, rgba(0,0,0,.22) 1.1px, transparent 1.5px) 0 0/6px 6px */
function halftone(ctx: Ctx, x: number, y: number, w: number, h: number) {
  ctx.save()
  ctx.beginPath()
  ctx.rect(x, y, w, h)
  ctx.clip()
  ctx.fillStyle = 'rgba(0,0,0,0.22)'
  for (let yy = y + 3; yy < y + h; yy += 6) {
    for (let xx = x + 3; xx < x + w; xx += 6) {
      ctx.beginPath()
      ctx.arc(xx, yy, 1.25, 0, Math.PI * 2)
      ctx.fill()
    }
  }
  ctx.restore()
}

/** 白字黑描边 + 墨影（.p-hero h3） */
function comicText(ctx: Ctx, text: string, x: number, y: number) {
  ctx.lineJoin = 'round'
  ctx.fillStyle = INK
  ctx.fillText(text, x + 3, y + 3)
  ctx.lineWidth = 3
  ctx.strokeStyle = INK
  ctx.strokeText(text, x, y)
  ctx.fillStyle = '#FFFFFF'
  ctx.fillText(text, x, y)
}

function balloon(ctx: Ctx, quote: string, x: number, bottom: number, maxW: number) {
  ctx.font = display(19)
  const lineH = 19 * 1.35
  const lines = wrapLines(quote, maxW - 36, (s) => ctx.measureText(s).width, 3)
  const textW = Math.max(...lines.map((l) => ctx.measureText(l).width))
  const w = Math.min(maxW, textW + 36)
  const h = lines.length * lineH + 24
  const y = bottom - h
  const cx = x + w / 2
  const cy = y + h / 2
  // 尾巴（右下）
  ctx.beginPath()
  ctx.moveTo(x + w - 58, y + h - 6)
  ctx.lineTo(x + w - 30, y + h + 15)
  ctx.lineTo(x + w - 40, y + h - 4)
  ctx.closePath()
  ctx.fillStyle = '#FFFFFF'
  ctx.fill()
  ctx.lineWidth = 2.5
  ctx.strokeStyle = INK
  ctx.stroke()
  // 椭圆气泡
  ctx.beginPath()
  ctx.ellipse(cx, cy, w / 2, h / 2, 0, 0, Math.PI * 2)
  ctx.fillStyle = '#FFFFFF'
  ctx.fill()
  ctx.stroke()
  ctx.fillStyle = INK
  ctx.textBaseline = 'middle'
  lines.forEach((l, i) => {
    ctx.fillText(l, cx - ctx.measureText(l).width / 2, y + 12 + lineH * (i + 0.5))
  })
}

function sunCode(ctx: Ctx, x: number, y: number, size: number) {
  const k = size / 100
  ctx.save()
  ctx.translate(x, y)
  ctx.scale(k, k)
  ctx.beginPath()
  ctx.arc(50, 50, 48, 0, Math.PI * 2)
  ctx.fillStyle = '#FFFFFF'
  ctx.fill()
  ctx.lineWidth = 2 / k
  ctx.strokeStyle = INK
  ctx.stroke()
  ctx.fillStyle = INK
  for (const d of sunCodeDots()) {
    ctx.beginPath()
    ctx.arc(d.x, d.y, 2.1, 0, Math.PI * 2)
    ctx.fill()
  }
  for (const [ex, ey] of SUN_CODE_EYES) {
    ctx.beginPath()
    ctx.arc(ex, ey, 8, 0, Math.PI * 2)
    ctx.fillStyle = '#FFFFFF'
    ctx.fill()
    ctx.lineWidth = 3
    ctx.stroke()
    ctx.beginPath()
    ctx.arc(ex, ey, 3.2, 0, Math.PI * 2)
    ctx.fillStyle = INK
    ctx.fill()
  }
  ctx.beginPath()
  ctx.arc(50, 50, 13, 0, Math.PI * 2)
  ctx.fillStyle = YELLOW
  ctx.fill()
  ctx.lineWidth = 2.5
  ctx.stroke()
  ctx.fillStyle = INK
  ctx.font = display(12)
  ctx.textBaseline = 'middle'
  ctx.fillText('懂', 50 - ctx.measureText('懂').width / 2, 51)
  ctx.restore()
}

export function drawPoster(ctx: Ctx, d: PosterData) {
  const W = POSTER_W
  const H = POSTER_H
  ctx.textBaseline = 'top'
  ctx.fillStyle = '#FFFFFF'
  ctx.fillRect(0, 0, W, H)
  strokeRect(ctx, 0, 0, W, H, 3)

  const pad = 15 // border 3 + padding 12
  const innerW = W - pad * 2

  // p-top
  ctx.fillStyle = INK
  ctx.font = display(18)
  ctx.textBaseline = 'middle'
  ctx.fillText('一话一懂', pad, pad + 9)
  ctx.font = body(13)
  ctx.fillStyle = MUTED
  const ep = `我的第 ${d.episode} 话`
  ctx.fillText(ep, W - pad - ctx.measureText(ep).width, pad + 9)

  // p-hero
  const heroY = pad + 18 + 10
  const heroH = 262
  ctx.fillStyle = YELLOW
  ctx.fillRect(pad, heroY, innerW, heroH)
  halftone(ctx, pad, heroY, innerW, heroH)
  strokeRect(ctx, pad, heroY, innerW, heroH, 2.5)
  ctx.font = display(46)
  ctx.textBaseline = 'top'
  const heroLines = wrapLines(`我看懂了\n${d.title}`, innerW - 32, (s) => ctx.measureText(s).width, 3)
  heroLines.forEach((l, i) => comicText(ctx, l, pad + 16, heroY + 16 + i * 46 * 1.05))
  balloon(ctx, d.quote, pad + 16, heroY + heroH - 24, 250)

  // p-stats
  const statsY = heroY + heroH + 8
  const boxW = (innerW - 6) / 2
  const boxH = 58
  ;[
    [`${d.correct} / ${d.total}`, '答对格数'],
    [d.duration, '用时']
  ].forEach(([value, label], i) => {
    const bx = pad + i * (boxW + 6)
    strokeRect(ctx, bx, statsY, boxW, boxH, 2)
    ctx.textBaseline = 'top'
    ctx.fillStyle = INK
    ctx.font = display(24)
    ctx.fillText(value, bx + 8, statsY + 8)
    ctx.fillStyle = MUTED
    ctx.font = body(12)
    ctx.fillText(label, bx + 8, statsY + 36)
  })

  // p-qr
  const qrTop = statsY + boxH + 10
  ctx.save()
  ctx.setLineDash([6, 4])
  ctx.lineWidth = 2
  ctx.strokeStyle = LINE
  ctx.beginPath()
  ctx.moveTo(pad, qrTop + 1)
  ctx.lineTo(W - pad, qrTop + 1)
  ctx.stroke()
  ctx.restore()
  const qrY = qrTop + 12
  sunCode(ctx, pad, qrY, 72)
  ctx.textBaseline = 'top'
  ctx.fillStyle = INK
  ctx.font = display(18)
  ctx.fillText('扫码，下一话你来', pad + 84, qrY + 16)
  ctx.fillStyle = MUTED
  ctx.font = body(12)
  ctx.fillText('输入任意知识，AI 帮你出题', pad + 84, qrY + 42)
}
