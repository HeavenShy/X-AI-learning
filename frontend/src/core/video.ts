/** 视频出题的纯逻辑：时间格式、时间段校验、B 站链接识别、选文件预检、处理步骤、失败文案 */

import { ErrorCode, type VideoJob } from '../types/api'
import { formatClock } from './format'
import { extractUrl } from './web'

export { formatClock }

export const VIDEO_MAX_BYTES = 200 * 1024 * 1024
export const VIDEO_MAX_SECONDS = 30 * 60
export const VIDEO_FOCUS_MAX = 200
export const VIDEO_EXTENSIONS = ['mp4', 'mov', 'm4v', 'webm', 'mkv', '3gp', 'avi', 'flv']

/** mm:ss / h:mm:ss / 纯分钟数（“5” = 5 分钟）→ 秒；中文冒号也认。格式不对返回 null */
export function parseClock(text: string): number | null {
  const t = (text || '').trim().replace(/：/g, ':')
  if (!t) return null
  if (/^\d+$/.test(t)) return Number(t) * 60
  const m = /^(?:(\d+):)?(\d{1,2}):(\d{1,2})$/.exec(t)
  if (!m) return null
  const [h, mi, s] = [Number(m[1] || 0), Number(m[2]), Number(m[3])]
  if (s >= 60 || (m[1] && mi >= 60)) return null
  return h * 3600 + mi * 60 + s
}

export interface RangeResult {
  start?: number
  end?: number
  error?: string
}

/** “只学其中一段”：两个都可以不填；填了要格式对、在视频时长内、结束晚于开始 */
export function validateRange(startText: string, endText: string, duration: number): RangeResult {
  const out: RangeResult = {}
  if (startText.trim()) {
    const v = parseClock(startText)
    if (v === null) return { error: '开始时间的格式不对，写成 02:10 这样' }
    out.start = v
  }
  if (endText.trim()) {
    const v = parseClock(endText)
    if (v === null) return { error: '结束时间的格式不对，写成 08:45 这样' }
    out.end = v
  }
  if (out.start !== undefined && duration > 0 && out.start >= duration) {
    return { error: `开始时间超出了视频长度（${formatClock(duration)}）` }
  }
  if (out.start !== undefined && out.end !== undefined && out.end <= out.start) {
    return { error: '结束时间要晚于开始时间' }
  }
  if (out.start === 0) delete out.start
  if (out.end !== undefined && duration > 0 && out.end >= duration) delete out.end
  return out
}

const BV_ONLY = /^\s*(BV[0-9A-Za-z]{10})\s*$/

function isBilibiliHost(url: string): boolean {
  const m = /^https?:\/\/([^/?#:]+)/i.exec(url)
  if (!m) return false
  const host = m[1].toLowerCase()
  return ['bilibili.com', 'b23.tv'].some((h) => host === h || host.endsWith(`.${h}`))
}

/** 从分享文案里取 B 站链接或 BV 号；没有返回 null（后端会再校验一次） */
export function extractBilibiliUrl(text: string): string | null {
  const bv = BV_ONLY.exec(text || '')
  if (bv) return `https://www.bilibili.com/video/${bv[1]}`
  const url = extractUrl(text)
  return url && isBilibiliHost(url) ? url : null
}

/** 首页输入框里整段就是一个 B 站链接或 BV 号 */
export function isBareBilibili(text: string): boolean {
  const t = (text || '').trim()
  if (BV_ONLY.test(t)) return true
  return extractUrl(t) === t && isBilibiliHost(t)
}

export interface PickedVideo {
  size: number
  /** 秒；从聊天选的文件没有 */
  duration?: number
  name?: string
}

export function fileExtension(name: string): string {
  const m = /\.([0-9a-z]+)$/i.exec(name || '')
  return m ? m[1].toLowerCase() : ''
}

/** 选完视频先在本地检查，返回错误文案或 null（后端同规则再校验） */
export function precheckVideo(v: PickedVideo): string | null {
  if (v.name && !VIDEO_EXTENSIONS.includes(fileExtension(v.name))) {
    return '只支持常见的视频文件（mp4、mov、m4v、webm、mkv、3gp 等）。'
  }
  if (v.size <= 0) return '这个文件是空的，换一个视频试试。'
  if (v.size > VIDEO_MAX_BYTES) return '视频超过 200 MB 了：先剪出想学的一段，或在微信里压缩后再上传。'
  if (v.duration !== undefined && v.duration > VIDEO_MAX_SECONDS + 1) {
    return '视频超过 30 分钟了：先剪出想学的一段再上传。'
  }
  return null
}

export type StepState = 'done' | 'doing' | 'wait'

export interface JobStep {
  title: string
  sub: string
  state: StepState
}

/**
 * 解析进度的三步。上传文件：上传（百分比）/ 提取音频 / 转文字；B 站：读取视频 / 提取音频 / 转文字。
 * job 为 null 时表示还在上传（uploadPercent 有值）或刚提交链接。
 */
export function jobSteps(source: 'upload' | 'bilibili', job: VideoJob | null, uploadPercent = 0): JobStep[] {
  const order = ['download', 'extract', 'transcribe', 'done'] as const
  // 上传：上传完（有了 job）第一步就完成；B 站：download 阶段是第一步
  let idx: number
  if (!job) idx = 0
  else if (job.status === 'ready') idx = 3
  else idx = Math.max(source === 'upload' ? 1 : 0, order.indexOf(job.stage))
  const state = (i: number): StepState => (idx > i ? 'done' : idx === i ? 'doing' : 'wait')
  const subtitled = job?.via === 'subtitle'
  const first =
    source === 'upload'
      ? { title: '上传视频', sub: job ? '已上传' : `${Math.floor(uploadPercent)}%` }
      : { title: '读取视频', sub: job && job.title !== 'B 站视频' ? job.title.slice(0, 16) : 'B 站视频信息与音频' }
  const transcribeSub = subtitled
    ? '用视频自带的字幕'
    : job && job.progress_total > 0
      ? `已转 ${job.progress_done} / ${job.progress_total} 段（每段 1 分钟）`
      : '把讲话转成文字'
  return [
    { ...first, state: state(0) },
    { title: '提取音频', sub: subtitled ? '有字幕，跳过' : '只取声音，不看画面', state: state(1) },
    { title: '转文字', sub: transcribeSub, state: state(2) }
  ]
}

/** 预览卡片第二行：时长 12:30 · 已转写约 3200 字（语音识别） */
export function readyLine(job: Pick<VideoJob, 'duration_seconds' | 'char_count' | 'via'>): string {
  const via = job.via === 'subtitle' ? '字幕' : '语音识别'
  return `时长 ${formatClock(job.duration_seconds)} · 已转写约 ${job.char_count} 字（${via}）`
}

export type VideoFix = 'upload' | 'paste' | 'retry'

export interface VideoErrorCopy {
  title: string
  text: string
  fixes: VideoFix[]
}

/** 处理失败（任务的 fail_reason）或接口报错时的原因与替代方式 */
export function videoErrorCopy(code: number | null, message: string, source: 'upload' | 'bilibili'): VideoErrorCopy {
  const text = message || '视频处理失败，请稍后重试。'
  if (code === ErrorCode.NETWORK) return { title: '网络好像断了', text: '没连上服务，检查网络后再试一次。', fixes: ['retry'] }
  if (code === ErrorCode.VIDEO_LINK_INVALID) return { title: '这个链接用不了', text, fixes: ['upload'] }
  if (code === ErrorCode.VIDEO_TOO_LARGE || code === ErrorCode.VIDEO_TYPE_NOT_SUPPORTED) {
    return { title: '这个视频传不了', text, fixes: [] }
  }
  if (code === ErrorCode.LIMIT_EXCEEDED) return { title: '还有一个视频在处理', text, fixes: [] }
  if (code === ErrorCode.PAGE_NO_CONTENT) return { title: '没听到可以学的内容', text, fixes: ['paste'] }
  if (code === ErrorCode.VIDEO_RANGE_EMPTY) return { title: '这段时间里没有讲话', text, fixes: [] }
  if (code === ErrorCode.NOT_FOUND || code === ErrorCode.VIDEO_NOT_READY) {
    return { title: '视频解析结果没了', text, fixes: [source === 'bilibili' ? 'retry' : 'upload'] }
  }
  // 后台处理失败（fail_reason）：按原因给替代方式
  if (/声音|讲话内容/.test(text)) return { title: '没听到讲话', text, fixes: ['paste'] }
  if (/B 站/.test(text)) return { title: 'B 站视频读不了', text, fixes: ['upload'] }
  if (/转文字服务|稍后/.test(text)) return { title: '这次没处理成', text, fixes: ['retry'] }
  return { title: '视频处理失败', text, fixes: source === 'bilibili' ? ['retry', 'upload'] : ['upload'] }
}

export const VIDEO_FIX_COPY: Record<VideoFix, { title: string; sub: string }> = {
  upload: { title: '改为上传视频文件', sub: '先把视频保存到手机，再从相册或聊天里选' },
  paste: { title: '粘贴要学的段落', sub: '回到首页，直接把文字贴进输入框' },
  retry: { title: '再试一次', sub: '服务偶尔会暂时不可用' }
}

/** 视频出的题对应的 B 站链接（出处带时间点和链接）；上传的视频或不是视频出题为 null */
export function videoUrlOf(quiz: { questions: { sources?: { url?: string | null; start_seconds?: number | null }[] }[] }): string | null {
  for (const q of quiz.questions) {
    for (const s of q.sources ?? []) if (s.start_seconds != null && s.url) return s.url
  }
  return null
}

/** 视频出题页地址，可带上要预填的 B 站链接 */
export const videoQuizPage = (url?: string | null) =>
  url ? `/pages/video-quiz/index?url=${encodeURIComponent(url)}` : '/pages/video-quiz/index'
