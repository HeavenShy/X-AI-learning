import { test } from 'node:test'
import assert from 'node:assert/strict'

import { groupMistakes, lastAnswerText, withoutMistake, wrongCountLabel } from '../src/core/review'
import type { MistakeItem, Question } from '../src/types/api'
import { judge, multiple, single } from './fixtures'

const item = (quizId: string, title: string, question: Question, wrongCount = 1): MistakeItem => ({
  quiz_id: quizId,
  quiz_title: title,
  question,
  last_selected_answers: ['B'],
  wrong_count: wrongCount,
  first_wrong_at: '2026-11-05T02:03:04Z'
})

test('按话分组，组顺序与组内顺序保持接口顺序，带组内题数', () => {
  const items = [
    item('quiz_new', 'Transformer', multiple),
    item('quiz_new', 'Transformer', single),
    item('quiz_old', 'RAG 入门', judge)
  ]
  const groups = groupMistakes(items)
  assert.deepEqual(
    groups.map((g) => [g.quizId, g.title, g.count, g.items.map((i) => i.question.id)]),
    [
      ['quiz_new', 'Transformer', 2, ['q3', 'q1']],
      ['quiz_old', 'RAG 入门', 1, ['q2']]
    ]
  )
})

test('同一话不相邻时也归到第一次出现的组', () => {
  const groups = groupMistakes([item('a', 'A', single), item('b', 'B', judge), item('a', 'A', multiple)])
  assert.deepEqual(
    groups.map((g) => [g.quizId, g.count]),
    [
      ['a', 2],
      ['b', 1]
    ]
  )
})

test('没有错题时没有分组', () => {
  assert.deepEqual(groupMistakes([]), [])
})

test('答错次数文案', () => {
  assert.equal(wrongCountLabel(1), '错 1 次')
  assert.equal(wrongCountLabel(2), '错 2 次')
})

test('去掉已掌握的错题：按 quiz_id + question_id 识别', () => {
  // 两话里都有 q1，只去掉指定那话的
  const items = [item('a', 'A', single), item('b', 'B', single), item('a', 'A', multiple)]
  const left = withoutMistake(items, { quiz_id: 'a', question_id: 'q1' })
  assert.deepEqual(
    left.map((i) => [i.quiz_id, i.question.id]),
    [
      ['b', 'q1'],
      ['a', 'q3']
    ]
  )
})

test('上次的答案：选项字母 / 判断题文字 / 未作答', () => {
  assert.equal(lastAnswerText(multiple, ['B', 'C']), '上次选了 B、C')
  assert.equal(lastAnswerText(single, ['C']), '上次选了 C')
  assert.equal(lastAnswerText(judge, ['A']), '上次选了“对”')
  assert.equal(lastAnswerText(single, []), '上次没作答')
})
