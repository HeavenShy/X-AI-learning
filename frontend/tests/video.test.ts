import { test } from 'node:test'
import assert from 'node:assert/strict'

import { formatSource } from '../src/core/kb'
import {
  extractBilibiliUrl,
  formatClock,
  isBareBilibili,
  jobSteps,
  parseClock,
  precheckVideo,
  readyLine,
  validateRange,
  videoErrorCopy,
  videoQuizPage,
  videoUrlOf
} from '../src/core/video'
import { ErrorCode, type VideoJob } from '../src/types/api'

const job = (extra: Partial<VideoJob> = {}): VideoJob => ({
  job_id: 'vj_1',
  source: 'upload',
  title: '复利入门',
  url: null,
  status: 'processing',
  stage: 'extract',
  progress_done: 0,
  progress_total: 0,
  duration_seconds: 750,
  via: null,
  char_count: 0,
  fail_reason: null,
  ...extra
})

test('formatClock / parseClock', () => {
  assert.equal(formatClock(0), '00:00')
  assert.equal(formatClock(130.9), '02:10')
  assert.equal(formatClock(3725), '1:02:05')
  assert.equal(parseClock('02:10'), 130)
  assert.equal(parseClock('2：10'), 130)
  assert.equal(parseClock('5'), 300)
  assert.equal(parseClock('1:02:05'), 3725)
  assert.equal(parseClock(''), null)
  assert.equal(parseClock('2:75'), null)
  assert.equal(parseClock('abc'), null)
})

test('validateRange', () => {
  assert.deepEqual(validateRange('', '', 750), {})
  assert.deepEqual(validateRange('02:10', '08:45', 750), { start: 130, end: 525 })
  // 从 0 开始、到结尾为止等于没填
  assert.deepEqual(validateRange('00:00', '20:00', 750), {})
  assert.match(validateRange('08:45', '02:10', 750).error ?? '', /晚于/)
  assert.match(validateRange('13:00', '', 750).error ?? '', /超出/)
  assert.match(validateRange('x', '', 750).error ?? '', /开始时间的格式/)
})

test('extractBilibiliUrl / isBareBilibili', () => {
  assert.equal(
    extractBilibiliUrl('【两分钟讲复利】 https://b23.tv/AbCdEf 复制此链接'),
    'https://b23.tv/AbCdEf'
  )
  assert.equal(extractBilibiliUrl(' BV1ns411w7tt '), 'https://www.bilibili.com/video/BV1ns411w7tt')
  assert.equal(extractBilibiliUrl('https://m.bilibili.com/video/BV1ns411w7tt'), 'https://m.bilibili.com/video/BV1ns411w7tt')
  assert.equal(extractBilibiliUrl('https://evilbilibili.com/x'), null)
  assert.equal(extractBilibiliUrl('https://v.qq.com/x'), null)
  assert.equal(isBareBilibili('https://www.bilibili.com/video/BV1ns411w7tt'), true)
  assert.equal(isBareBilibili('BV1ns411w7tt'), true)
  assert.equal(isBareBilibili('https://example.com/a'), false)
  assert.equal(isBareBilibili('看 https://b23.tv/x'), false)
})

test('precheckVideo', () => {
  assert.equal(precheckVideo({ size: 1000, duration: 60, name: 'a.mp4' }), null)
  assert.match(precheckVideo({ size: 1000, name: 'a.pdf' }) ?? '', /常见的视频/)
  assert.match(precheckVideo({ size: 201 * 1024 * 1024 }) ?? '', /200 MB/)
  assert.match(precheckVideo({ size: 1000, duration: 1900 }) ?? '', /30 分钟/)
  assert.match(precheckVideo({ size: 0 }) ?? '', /空的/)
})

test('jobSteps 上传与 B 站', () => {
  assert.deepEqual(
    jobSteps('upload', null, 42.6).map((s) => [s.state, s.sub]),
    [['doing', '42%'], ['wait', '只取声音，不看画面'], ['wait', '把讲话转成文字']]
  )
  const transcribing = job({ stage: 'transcribe', progress_done: 3, progress_total: 13, via: 'asr' })
  assert.deepEqual(
    jobSteps('upload', transcribing).map((s) => s.state),
    ['done', 'done', 'doing']
  )
  assert.equal(jobSteps('upload', transcribing)[2].sub, '已转 3 / 13 段（每段 1 分钟）')
  assert.deepEqual(
    jobSteps('bilibili', job({ source: 'bilibili', stage: 'download', title: 'B 站视频' })).map((s) => s.state),
    ['doing', 'wait', 'wait']
  )
  const subs = jobSteps('bilibili', job({ source: 'bilibili', status: 'ready', stage: 'done', via: 'subtitle' }))
  assert.deepEqual(subs.map((s) => s.state), ['done', 'done', 'done'])
  assert.equal(subs[1].sub, '有字幕，跳过')
})

test('readyLine', () => {
  assert.equal(readyLine({ duration_seconds: 750, char_count: 3200, via: 'asr' }), '时长 12:30 · 已转写约 3200 字（语音识别）')
  assert.equal(readyLine({ duration_seconds: 75, char_count: 300, via: 'subtitle' }), '时长 01:15 · 已转写约 300 字（字幕）')
})

test('videoErrorCopy 按原因给替代方式', () => {
  assert.deepEqual(videoErrorCopy(null, '这个视频没有声音，没法按讲话内容出题。', 'upload').fixes, ['paste'])
  assert.deepEqual(videoErrorCopy(null, '这个 B 站视频读不了（可能要登录）', 'bilibili').fixes, ['upload'])
  assert.deepEqual(videoErrorCopy(null, '转文字服务暂时不可用，请稍后重试。', 'upload').fixes, ['retry'])
  assert.deepEqual(videoErrorCopy(ErrorCode.VIDEO_LINK_INVALID, '只支持 B 站', 'bilibili').fixes, ['upload'])
  assert.deepEqual(videoErrorCopy(ErrorCode.NOT_FOUND, '过期了', 'upload').fixes, ['upload'])
  assert.deepEqual(videoErrorCopy(ErrorCode.VIDEO_RANGE_EMPTY, '没有讲话', 'upload').fixes, [])
  assert.equal(videoErrorCopy(ErrorCode.NETWORK, '', 'upload').title, '网络好像断了')
})

test('videoUrlOf / videoQuizPage / formatSource', () => {
  const src = (extra: object) => ({ document_id: 'v', document_name: '复利入门', page: null, quote: 'q', ...extra })
  assert.equal(
    videoUrlOf({ questions: [{ sources: [src({ url: 'https://www.bilibili.com/video/BV1', start_seconds: 70 })] }] }),
    'https://www.bilibili.com/video/BV1'
  )
  // 网页出处有 url 但没有时间点，不算视频
  assert.equal(videoUrlOf({ questions: [{ sources: [src({ url: 'https://a.com' })] }] }), null)
  assert.equal(videoQuizPage(), '/pages/video-quiz/index')
  assert.equal(formatSource(src({ start_seconds: 130 })), '出处：视频《复利入门》02:10')
  assert.equal(formatSource(src({ start_seconds: 0, url: 'https://www.bilibili.com/video/BV1' })), '出处：视频《复利入门》00:00')
})
