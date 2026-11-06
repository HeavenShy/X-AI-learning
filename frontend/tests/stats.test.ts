import { test } from 'node:test'
import assert from 'node:assert/strict'

import { barHeights, canRetry, compareText, isWeakType, masteryClass, retryInput } from '../src/core/stats'
import type { StatsBar, TreeQuiz } from '../src/types/api'

const bar = (minutes: number): StatsBar => ({ label: '一', minutes, is_current: false })

const quiz = (over: Partial<TreeQuiz> = {}): TreeQuiz => ({
  quiz_id: 'quiz_1',
  title: '基金定投',
  user_input: '我想搞懂基金定投怎么算手续费',
  correct: 2,
  total: 5,
  accuracy: 40,
  weak_points: ['申购费率', '复利周期'],
  finished_at: '2026-11-05T02:03:04Z',
  ...over
})

test('柱高按最高那根换算，有时长的最矮 4%', () => {
  assert.deepEqual(barHeights([bar(8), bar(0), bar(16)]), [50, 0, 100])
  assert.deepEqual(barHeights([bar(1), bar(100)]), [4, 100])
  assert.deepEqual(barHeights([bar(0), bar(0)]), [0, 0])
  assert.deepEqual(barHeights([]), [])
})

test('与上一周期对比的文案', () => {
  assert.equal(compareText('week', 46, 34), '分钟，比上周多 12 分钟')
  assert.equal(compareText('month', 10, 30), '分钟，比上月少 20 分钟')
  assert.equal(compareText('week', 5, 5), '分钟，和上周一样')
  assert.equal(compareText('all', 120, null), '分钟')
})

test('掌握度着色阈值与报告页一致', () => {
  assert.equal(masteryClass(100), 'g')
  assert.equal(masteryClass(80), 'g')
  assert.equal(masteryClass(79), 'y')
  assert.equal(masteryClass(60), 'y')
  assert.equal(masteryClass(59), 'r')
  assert.equal(masteryClass(0), 'r')
})

test('题型标红：做过且低于 60%', () => {
  assert.equal(isWeakType({ type: 'multiple', correct: 1, total: 3, accuracy: 33 }), true)
  assert.equal(isWeakType({ type: 'judge', correct: 0, total: 0, accuracy: 0 }), false)
  assert.equal(isWeakType({ type: 'single', correct: 3, total: 5, accuracy: 60 }), false)
})

test('只有红色的话能再闯一轮', () => {
  assert.equal(canRetry(quiz()), true)
  assert.equal(canRetry(quiz({ accuracy: 60 })), false)
})

test('再闯一轮的出题输入', () => {
  assert.equal(retryInput(quiz()), '基金定投：重点练 申购费率、复利周期')
  assert.equal(retryInput(quiz({ weak_points: [] })), '我想搞懂基金定投怎么算手续费')
  // 知识库出题没填重点：原输入为空
  assert.equal(retryInput(quiz({ weak_points: [], user_input: '', title: '复利' })), '复利：再出一组题')
  assert.equal(Array.from(retryInput(quiz({ weak_points: ['长'.repeat(3000)] }))).length, 2000)
})
