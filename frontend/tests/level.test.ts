import { test } from 'node:test'
import assert from 'node:assert/strict'

import { applyGain, levelOf, levelProgressView, xpBarPercent } from '../src/core/level'

test('等级门槛：路人 0 / 龙套 150 / 配角 400 / 主角 1000 / 传说 2000', () => {
  assert.equal(levelOf(0).label, 'Lv.1 路人')
  assert.equal(levelOf(149).label, 'Lv.1 路人')
  assert.equal(levelOf(150).label, 'Lv.2 龙套')
  assert.equal(levelOf(399).label, 'Lv.2 龙套')
  assert.equal(levelOf(400).label, 'Lv.3 配角')
  assert.equal(levelOf(1000).label, 'Lv.4 主角')
  assert.equal(levelOf(2000).label, 'Lv.5 传说')
  assert.equal(levelOf(99999).next, null)
})

test('经验条按“当前经验 / 下一级门槛”计算（原型 370/400 ≈ 92%）', () => {
  assert.equal(Math.floor(xpBarPercent(370)), 92)
  assert.equal(xpBarPercent(0), 0)
  assert.equal(xpBarPercent(5000), 100)
})

test('结算：升级', () => {
  const r = applyGain(370, 40)
  assert.equal(r.xpAfter, 410)
  assert.equal(r.leveledUp, true)
  const view = levelProgressView(r)
  assert.deepEqual(view, {
    left: 'Lv.2 龙套',
    right: 'Lv.3 配角',
    percent: 100,
    note: '经验 410 / 400，已升到配角。下一级还差 590 经验。'
  })
})

test('结算：没升级只显示经验进度', () => {
  const view = levelProgressView(applyGain(200, 40))
  assert.equal(view.left, 'Lv.2 龙套')
  assert.equal(view.right, 'Lv.3 配角')
  assert.equal(view.percent, 60)
  assert.equal(view.note, '经验 240 / 400，再得 160 经验升到配角。')
})

test('结算：升到最高级', () => {
  const view = levelProgressView(applyGain(1990, 20))
  assert.equal(view.right, 'Lv.5 传说')
  assert.equal(view.note, '经验 2010，已升到传说，这是最高等级。')
})

test('结算：已是最高级', () => {
  const r = applyGain(2500, 10)
  assert.equal(r.leveledUp, false)
  assert.deepEqual(levelProgressView(r), { left: 'Lv.5 传说', right: '', percent: 100, note: '经验 2510，已是最高等级传说。' })
})
