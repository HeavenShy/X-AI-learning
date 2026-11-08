import { test } from 'node:test'
import assert from 'node:assert/strict'

import { formatSource } from '../src/core/kb'
import { extractUrl, isBareUrl, previewLine, webErrorCopy, urlTarget, webQuizPage, webUrlOf } from '../src/core/web'
import { ErrorCode } from '../src/types/api'

test('extractUrl 从分享文案里取链接', () => {
  assert.equal(extractUrl('https://mp.weixin.qq.com/s/abc'), 'https://mp.weixin.qq.com/s/abc')
  assert.equal(extractUrl('【一文看懂 RAG】https://b23.tv/xyz 复制此链接'), 'https://b23.tv/xyz')
  assert.equal(extractUrl('看这篇：https://example.com/a?b=1&c=2，写得很好'), 'https://example.com/a?b=1&c=2')
  assert.equal(extractUrl('(see http://example.com/wiki/RAG).'), 'http://example.com/wiki/RAG')
  assert.equal(extractUrl('“https://example.com/x”'), 'https://example.com/x')
  assert.equal(extractUrl('HTTPS://EXAMPLE.COM/A'), 'HTTPS://EXAMPLE.COM/A')
})

test('extractUrl 没有链接时为 null', () => {
  assert.equal(extractUrl(''), null)
  assert.equal(extractUrl('什么是 RAG'), null)
  assert.equal(extractUrl('example.com'), null)
  assert.equal(extractUrl('https://'), null)
  assert.equal(extractUrl('ftp://example.com/a'), null)
})

test('isBareUrl 只认整段就是一个链接', () => {
  assert.equal(isBareUrl('  https://example.com/a  '), true)
  assert.equal(isBareUrl('看看 https://example.com/a'), false)
  assert.equal(isBareUrl(''), false)
})

test('previewLine', () => {
  assert.equal(previewLine({ char_count: 6800, read_minutes: 15 }), '约 6800 字，读完要 15 分钟')
  assert.equal(previewLine({ char_count: 23000, read_minutes: 51 }), '约 2.3 万字，读完要 51 分钟')
})

test('webErrorCopy 按错误码给替代方式', () => {
  assert.deepEqual(webErrorCopy(ErrorCode.PAGE_NO_CONTENT, '读不出正文').fixes, ['paste'])
  assert.deepEqual(webErrorCopy(ErrorCode.PAGE_UNREACHABLE, '打不开').fixes, ['retry', 'paste'])
  assert.deepEqual(webErrorCopy(ErrorCode.PAGE_NOT_SUPPORTED, '这是一个 PDF 文件').fixes, ['kb'])
  assert.deepEqual(webErrorCopy(ErrorCode.PAGE_NOT_SUPPORTED, '网页太大了').fixes, [])
  assert.equal(webErrorCopy(ErrorCode.URL_INVALID, '链接格式不对').text, '链接格式不对')
  assert.deepEqual(webErrorCopy(ErrorCode.NETWORK, '').fixes, ['retry'])
  assert.equal(webErrorCopy(null, '').title, '读取失败')
})

test('formatSource 网页出处', () => {
  const base = { document_id: 'web_1', document_name: '一文看懂 RAG', page: null, quote: 'x' }
  assert.equal(formatSource({ ...base, url: 'https://example.com' }), '出处：网页《一文看懂 RAG》')
  assert.equal(formatSource({ ...base, document_name: '手册.pdf', page: 3, url: null }), '出处：手册.pdf，第 3 页')
})

test('webUrlOf 与 webQuizPage', () => {
  const src = (url?: string | null) => ({ document_id: 'd', document_name: 'n', page: null, quote: 'q', url })
  assert.equal(webUrlOf({ questions: [{ sources: [] }, { sources: [src('https://a.com/x')] }] }), 'https://a.com/x')
  assert.equal(webUrlOf({ questions: [{ sources: [src(null)] }, {}] }), null)
  assert.equal(webQuizPage(), '/pages/web-quiz/index')
  assert.equal(webQuizPage('https://a.com/x?y=1'), '/pages/web-quiz/index?url=https%3A%2F%2Fa.com%2Fx%3Fy%3D1')
})

test('urlTarget 接受链接和像域名的输入', () => {
  assert.equal(urlTarget('看 https://a.com/x 这篇'), 'https://a.com/x')
  assert.equal(urlTarget(' mp.weixin.qq.com/s/abc '), 'mp.weixin.qq.com/s/abc')
  assert.equal(urlTarget('baike.baidu.com'), 'baike.baidu.com')
  assert.equal(urlTarget('什么是 RAG'), null)
  assert.equal(urlTarget('3.14'), null)
  assert.equal(urlTarget(''), null)
})
