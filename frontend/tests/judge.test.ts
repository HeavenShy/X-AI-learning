import { test } from 'node:test'
import assert from 'node:assert/strict'

import { answerLine, judgeAnswer, optionVisual, resultTitle } from '../src/core/judge'
import { judge, multiple, single } from './fixtures'

test('单选答对', () => {
  const r = judgeAnswer(single, ['A'])
  assert.equal(r.isCorrect, true)
  assert.deepEqual(single.options.map((o) => optionVisual(single, r, o.key)), [
    { state: 'right', order: 1 },
    { state: 'dim', order: 0 },
    { state: 'dim', order: 0 },
    { state: 'dim', order: 0 }
  ])
  assert.equal(resultTitle(single, r), '答对了')
})

test('单选答错：选中项标错，正确项标对', () => {
  const r = judgeAnswer(single, ['C'])
  assert.equal(r.isCorrect, false)
  assert.deepEqual(optionVisual(single, r, 'C'), { state: 'wrong', order: 1 })
  assert.deepEqual(optionVisual(single, r, 'A'), { state: 'right', order: 2 })
  assert.equal(resultTitle(single, r), '答错了，正确答案是 A')
})

test('多选答错：依次标出选错、选对、漏选（原型第 12 屏）', () => {
  const r = judgeAnswer(multiple, ['B', 'C'])
  assert.equal(r.isCorrect, false)
  assert.deepEqual(r.missed, ['A'])
  assert.deepEqual(r.wrongPicked, ['B'])
  assert.deepEqual(multiple.options.map((o) => optionVisual(multiple, r, o.key)), [
    { state: 'missed', order: 3 },
    { state: 'wrong', order: 1 },
    { state: 'right', order: 2 },
    { state: 'dim', order: 0 }
  ])
  assert.equal(resultTitle(multiple, r), '差一点，漏了 A')
})

test('多选：选多了但没漏选', () => {
  const r = judgeAnswer(multiple, ['A', 'C', 'D'])
  assert.equal(r.isCorrect, false)
  assert.equal(resultTitle(multiple, r), '多选了 D')
})

test('多选：选项顺序无关', () => {
  assert.equal(judgeAnswer(multiple, ['C', 'A']).isCorrect, true)
})

test('判断题', () => {
  assert.equal(judgeAnswer(judge, ['B']).isCorrect, true)
  const r = judgeAnswer(judge, ['A'])
  assert.equal(resultTitle(judge, r), '答错了，这个说法不对')
})

test('正确答案行', () => {
  assert.equal(answerLine(multiple), '正确答案：A、C')
  assert.equal(answerLine(judge), '正确答案：错')
})
