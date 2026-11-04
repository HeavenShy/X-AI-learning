import { test } from 'node:test'
import assert from 'node:assert/strict'

import {
  advance,
  answerCurrent,
  cellStates,
  createSession,
  currentQuestion,
  isLastQuestion,
  resumeTitle,
  sessionStats,
  toAnswerRecords
} from '../src/core/session'
import { quiz } from './fixtures'

const T0 = 1_700_000_000_000

test('新会话从第 1 格开始', () => {
  const s = createSession(quiz, 'mixed', T0)
  assert.equal(s.index, 0)
  assert.equal(currentQuestion(s).id, 'q1')
  assert.deepEqual(cellStates(s), ['now', '', ''])
  assert.equal(s.finished, false)
})

test('答题后记录对错和用时，格子变色', () => {
  let s = createSession(quiz, 'mixed', T0)
  s = answerCurrent(s, ['A'], 3200, T0 + 3200)
  assert.deepEqual(s.answers.q1, { selected: ['A'], isCorrect: true, durationMs: 3200 })
  assert.deepEqual(cellStates(s), ['ok', '', ''])
  s = advance(s, T0 + 4000)
  assert.deepEqual(cellStates(s), ['ok', 'now', ''])
  s = answerCurrent(s, ['A'], 1000, T0 + 5000)
  assert.deepEqual(cellStates(s), ['ok', 'no', ''])
})

test('同一题不能重复作答', () => {
  let s = createSession(quiz, 'mixed', T0)
  s = answerCurrent(s, ['B'], 1000, T0)
  s = answerCurrent(s, ['A'], 1000, T0)
  assert.equal(s.answers.q1.isCorrect, false)
})

test('未作答不能前进', () => {
  const s = advance(createSession(quiz, 'mixed', T0), T0)
  assert.equal(s.index, 0)
})

test('最后一题之后会话完成；统计经验与金币', () => {
  let s = createSession(quiz, 'mixed', T0)
  s = advance(answerCurrent(s, ['A'], 1000, T0), T0)
  s = advance(answerCurrent(s, ['B'], 2000, T0), T0)
  assert.equal(isLastQuestion(s), true)
  s = answerCurrent(s, ['A'], 3000, T0)
  s = advance(s, T0)
  assert.equal(s.finished, true)
  const st = sessionStats(s)
  assert.deepEqual(st, { correct: 2, total: 3, answered: 3, accuracy: 67, durationMs: 6000, xp: 20, coins: 10 })
})

test('转成报告接口的答题记录', () => {
  let s = createSession(quiz, 'mixed', T0)
  s = advance(answerCurrent(s, ['A'], 1000, T0), T0)
  assert.deepEqual(toAnswerRecords(s), [{ question_id: 'q1', selected_answers: ['A'], is_correct: true, duration_ms: 1000 }])
})

test('续答标题', () => {
  let s = createSession(quiz, 'mixed', T0)
  s = advance(answerCurrent(s, ['A'], 1000, T0), T0)
  s = advance(answerCurrent(s, ['A'], 1000, T0), T0)
  assert.equal(resumeTitle(s), 'RAG 入门，看到第 3 格')
})
