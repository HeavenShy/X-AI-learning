import { test } from 'node:test'
import assert from 'node:assert/strict'

import {
  KB_MAX_FILE_BYTES,
  MSG_FILE_EMPTY,
  MSG_FILE_TOO_LARGE,
  MSG_TYPE_NOT_SUPPORTED,
  cleanKbName,
  defaultSelection,
  documentSubline,
  fileExtension,
  formatSize,
  formatSource,
  hasProcessing,
  kbSubline,
  precheckFile,
  quotaPercent,
  selectedIds,
  STATUS_LABEL,
  STATUS_PILL,
  toggleSelection,
  updatedLabel,
  validateKbName
} from '../src/core/kb'
import type { KbDocument, KnowledgeBase } from '../src/types/api'

const doc = (id: string, status: KbDocument['status'], extra: Partial<KbDocument> = {}): KbDocument => ({
  document_id: id,
  filename: `${id}.pdf`,
  file_type: 'pdf',
  size_bytes: 1000,
  status,
  fail_reason: status === 'failed' ? '读不出文字，可能是扫描件或图片版 PDF，请上传文字版' : null,
  page_count: status === 'ready' ? 9 : null,
  char_count: status === 'ready' ? 1234 : 0,
  created_at: '2026-11-05T02:03:04Z',
  ...extra
})

// ---------- 上传预检 ----------

test('支持的扩展名（不分大小写）通过预检', () => {
  for (const name of ['手册.pdf', 'a.DOCX', 'notes.txt', 'README.md', '多.个.点.Pdf']) {
    assert.equal(precheckFile({ name, size: 100 }), null, name)
  }
})

test('不支持的类型被拦下', () => {
  for (const name of ['slides.pptx', 'photo.png', 'old.doc', 'noext', 'archive.zip']) {
    assert.equal(precheckFile({ name, size: 100 }), MSG_TYPE_NOT_SUPPORTED, name)
  }
})

test('空文件与超过 20 MB 被拦下，正好 20 MB 可以', () => {
  assert.equal(precheckFile({ name: 'a.pdf', size: 0 }), MSG_FILE_EMPTY)
  assert.equal(precheckFile({ name: 'a.pdf', size: KB_MAX_FILE_BYTES + 1 }), MSG_FILE_TOO_LARGE)
  assert.equal(precheckFile({ name: 'a.pdf', size: 21 * 1024 * 1024 }), MSG_FILE_TOO_LARGE)
  assert.equal(precheckFile({ name: 'a.pdf', size: KB_MAX_FILE_BYTES }), null)
})

test('fileExtension', () => {
  assert.equal(fileExtension('a.b.PDF'), 'pdf')
  assert.equal(fileExtension('noext'), '')
})

// ---------- 名称 ----------

test('知识库名称 1–20 字，去首尾空白', () => {
  assert.equal(validateKbName('  公司新人考核 '), null)
  assert.equal(validateKbName('   '), '知识库名称不能为空')
  assert.equal(validateKbName('字'.repeat(20)), null)
  assert.equal(validateKbName('字'.repeat(21)), '知识库名称最多 20 个字')
  assert.equal(cleanKbName('  PMP   备考 '), 'PMP 备考')
})

// ---------- 状态与文案 ----------

test('状态文案与颜色', () => {
  assert.deepEqual(STATUS_LABEL, { processing: '处理中', ready: '可出题', failed: '失败' })
  assert.deepEqual(STATUS_PILL, { processing: 'run', ready: 'ok', failed: 'no' })
})

test('资料第二行：页数字数 / 处理中提示 / 失败原因', () => {
  assert.equal(documentSubline(doc('a', 'ready')), '9 页，1234 字')
  assert.equal(documentSubline(doc('b', 'ready', { page_count: null, char_count: 25300, file_type: 'docx' })), '2.5 万字')
  assert.equal(documentSubline(doc('c', 'ready', { page_count: null, char_count: 30000 })), '3 万字')
  assert.match(documentSubline(doc('d', 'processing')), /正在提取文字/)
  assert.equal(documentSubline(doc('e', 'failed')), '读不出文字，可能是扫描件或图片版 PDF，请上传文字版')
})

test('formatSource：有页码 / 没页码', () => {
  assert.equal(
    formatSource({ document_id: 'd', document_name: '员工手册.pdf', page: 6, quote: 'x' }),
    '出处：员工手册.pdf，第 6 页'
  )
  assert.equal(formatSource({ document_id: 'd', document_name: '报销制度.docx', page: null, quote: 'x' }), '出处：报销制度.docx')
})

test('formatSize', () => {
  assert.equal(formatSize(512), '512 B')
  assert.equal(formatSize(2048), '2 KB')
  assert.equal(formatSize(2.5 * 1024 * 1024), '2.5 MB')
})

// ---------- 轮询与勾选 ----------

test('hasProcessing', () => {
  assert.equal(hasProcessing([doc('a', 'ready'), doc('b', 'failed')]), false)
  assert.equal(hasProcessing([doc('a', 'ready'), doc('b', 'processing')]), true)
  assert.equal(hasProcessing([]), false)
})

test('默认勾选全部可出题资料，未就绪的不能勾', () => {
  const docs = [doc('a', 'ready'), doc('b', 'ready'), doc('c', 'processing'), doc('d', 'failed')]
  assert.deepEqual(defaultSelection(docs), ['a', 'b'])
  assert.deepEqual(toggleSelection(['a', 'b'], docs[2]), ['a', 'b'])
  assert.deepEqual(toggleSelection(['a', 'b'], docs[3]), ['a', 'b'])
  assert.deepEqual(toggleSelection(['a', 'b'], docs[0]), ['b'])
  assert.deepEqual(toggleSelection(['b'], docs[0]), ['b', 'a'])
})

test('全选时传空数组（整个库），否则传勾选的 id', () => {
  const docs = [doc('a', 'ready'), doc('b', 'ready'), doc('c', 'processing')]
  assert.deepEqual(selectedIds(docs, ['a', 'b']), [])
  assert.deepEqual(selectedIds(docs, ['b', 'a']), [])
  assert.deepEqual(selectedIds(docs, ['b']), ['b'])
  assert.deepEqual(selectedIds(docs, ['b', 'c']), ['b'])
  assert.deepEqual(selectedIds(docs, []), [])
})

// ---------- 列表 ----------

// 本机时区是 Australia/Sydney：用本地时间构造，不写死时区
const NOW = new Date(2026, 10, 6, 15, 0).getTime()
const iso = (y: number, m: number, d: number, h = 10) => new Date(y, m, d, h).toISOString()

test('更新时间文案', () => {
  assert.equal(updatedLabel(iso(2026, 10, 6, 1), NOW), '今天更新')
  assert.equal(updatedLabel(iso(2026, 10, 5, 23), NOW), '昨天更新')
  assert.equal(updatedLabel(iso(2026, 10, 3), NOW), '3 天前更新')
  assert.equal(updatedLabel(iso(2026, 9, 20), NOW), '10 月 20 日更新')
})

test('知识库第二行', () => {
  const kb = (n: number): KnowledgeBase => ({
    kb_id: 'kb_1',
    name: '甲',
    document_count: n,
    ready_count: n,
    created_at: iso(2026, 10, 1),
    updated_at: iso(2026, 10, 5)
  })
  assert.equal(kbSubline(kb(12), NOW), '12 份资料，昨天更新')
  assert.equal(kbSubline(kb(0), NOW), '还没有资料，昨天更新')
})

test('资料用量百分比', () => {
  assert.equal(quotaPercent(18, 50), 36)
  assert.equal(quotaPercent(60, 50), 100)
  assert.equal(quotaPercent(0, 0), 0)
})
