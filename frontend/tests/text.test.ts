import { test } from 'node:test'
import assert from 'node:assert/strict'

import { wrapLines } from '../src/core/text'

// 每个字符宽 10，便于断言
const measure = (s: string) => Array.from(s).length * 10

test('不超宽不折行', () => {
  assert.deepEqual(wrapLines('把知识做成关卡', 100, measure), ['把知识做成关卡'])
})

test('按宽度逐字折行', () => {
  assert.deepEqual(wrapLines('把知识做成关卡，记忆会更深。', 70, measure), ['把知识做成关卡', '，记忆会更深。'])
})

test('保留手动换行', () => {
  assert.deepEqual(wrapLines('我看懂了\nRAG', 200, measure), ['我看懂了', 'RAG'])
})

test('英文单词尽量不拆开', () => {
  assert.deepEqual(wrapLines('学会 Transformer 架构', 120, measure), ['学会 ', 'Transformer ', '架构'])
})

test('超过最大行数时截断并加省略号', () => {
  assert.deepEqual(wrapLines('一二三四五六七八九十', 30, measure, 2), ['一二三', '四五…'])
})
