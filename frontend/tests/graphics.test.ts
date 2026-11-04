import { test } from 'node:test'
import assert from 'node:assert/strict'

import { base64Ascii, burstPoints, sunCodeDots, svgUri } from '../src/core/graphics'

test('ASCII base64 与 Node Buffer 一致', () => {
  for (const s of ['', 'a', 'ab', 'abc', '<svg viewBox="0 0 24 24"><path d="M1 2"/></svg>']) {
    assert.equal(base64Ascii(s), Buffer.from(s, 'ascii').toString('base64'))
  }
})

test('svgUri 生成 base64 data URI', () => {
  assert.equal(svgUri('<svg/>'), `data:image/svg+xml;base64,${Buffer.from('<svg/>').toString('base64')}`)
})

test('svgUri 拒绝非 ASCII（避免小程序里编码出错）', () => {
  assert.throws(() => svgUri('<svg>懂</svg>'))
})

test('爆炸框顶点：数量为 2n，与原型 proto.js 的算法一致', () => {
  const pts = burstPoints(16, 56, 36, 120, 100)
  assert.equal(pts.length, 32)
  // 第一个点在正上方：x = cx, y = cy - R * 0.85
  assert.deepEqual(pts[0], [60, 2.4])
})

test('太阳码点阵稳定（同一种子结果相同）', () => {
  const a = sunCodeDots()
  const b = sunCodeDots()
  assert.deepEqual(a, b)
  assert.ok(a.length > 50)
  for (const d of a) {
    assert.ok(d.x > 0 && d.x < 100 && d.y > 0 && d.y < 100)
  }
})
