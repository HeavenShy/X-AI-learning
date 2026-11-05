import { test } from 'node:test'
import assert from 'node:assert/strict'

import {
  displayTopic,
  estimateMinutes,
  formatDuration,
  formatInterrupted,
  planText,
  validateInput,
  visibleLength
} from '../src/core/format'

test('用时格式（原型：3 分 12 秒）', () => {
  assert.equal(formatDuration(192_000), '3 分 12 秒')
  assert.equal(formatDuration(40_400), '40 秒')
  assert.equal(formatDuration(0), '0 秒')
  assert.equal(formatDuration(120_000), '2 分 0 秒')
})

test('中断时间（原型：昨天 23:10 中断）', () => {
  const now = new Date(2026, 10, 4, 9, 0).getTime()
  assert.equal(formatInterrupted(new Date(2026, 10, 3, 23, 10).getTime(), now), '昨天 23:10 中断')
  assert.equal(formatInterrupted(new Date(2026, 10, 4, 8, 5).getTime(), now), '今天 08:05 中断')
  assert.equal(formatInterrupted(new Date(2026, 10, 1, 7, 30).getTime(), now), '11 月 1 日 07:30 中断')
})

test('出题中页面展示的主题去掉“我想学习”前缀（原型第 5 屏）', () => {
  assert.equal(displayTopic('我想学习什么是 RAG，以及它和传统搜索有什么区别'), '什么是 RAG，以及它和传统搜索有什么区别')
  assert.equal(displayTopic('  复利是怎么算的。'), '复利是怎么算的')
  assert.equal(displayTopic('我想了解碳中和'), '碳中和')
})

test('题量对应的预计时长与题型配比', () => {
  assert.equal(estimateMinutes(3), 2)
  assert.equal(estimateMinutes(5), 4)
  assert.equal(estimateMinutes(10), 8)
  assert.equal(planText(5), '单选 3、多选 1、判断 1')
  assert.equal(planText(10), '单选 6、多选 2、判断 2')
})

test('输入校验：至少 4 个字（不计空白）', () => {
  assert.equal(visibleLength('R A G'), 3)
  assert.match(validateInput('RAG') ?? '', /至少写 4 个字/)
  assert.match(validateInput('  R A G ') ?? '', /至少写 4 个字/)
  assert.equal(validateInput('RAG 是啥'), null)
})
