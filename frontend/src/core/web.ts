/** 网页出题的纯逻辑：从分享文案里抠链接、预览文案、预览失败时的原因与替代方式 */

import { ErrorCode, type WebPreview } from '../types/api'
import { formatChars } from './kb'

export const WEB_FOCUS_MAX = 200

// 链接里不会出现的字符：空白、引号、尖括号，以及中文标点（分享文案常把链接和中文贴在一起）
const URL_RE = /https?:\/\/[^\s<>"'`，。！？、；：（）【】《》「」『』“”‘’]+/i
// 结尾常粘着的英文标点不算链接的一部分
const TRAILING = /[.,;:!?)\]}]+$/

/** 从一段文字（剪贴板、分享文案）里取出第一个 http(s) 链接；没有返回 null */
export function extractUrl(text: string): string | null {
  const m = URL_RE.exec(text || '')
  if (!m) return null
  const url = m[0].replace(TRAILING, '')
  return url.length > 'https://'.length ? url : null
}

/** 整段输入就是一个链接（首页输入框里贴了网址） */
export function isBareUrl(text: string): boolean {
  const t = (text || '').trim()
  return t.length > 0 && extractUrl(t) === t
}

/** 预览卡片第二行：约 6800 字，读完要 15 分钟 */
export function previewLine(p: Pick<WebPreview, 'char_count' | 'read_minutes'>): string {
  return `约 ${formatChars(p.char_count)}，读完要 ${p.read_minutes} 分钟`
}

export type WebFix = 'retry' | 'paste' | 'kb'

export interface WebErrorCopy {
  title: string
  text: string
  fixes: WebFix[]
}

/** 预览 / 出题失败时展示的原因和替代方式。message 是后端给的具体原因 */
export function webErrorCopy(code: number | null, message: string): WebErrorCopy {
  switch (code) {
    case ErrorCode.URL_INVALID:
      return { title: '这个链接用不了', text: message, fixes: [] }
    case ErrorCode.PAGE_UNREACHABLE:
      return { title: '网页打不开', text: message, fixes: ['retry', 'paste'] }
    case ErrorCode.PAGE_NO_CONTENT:
      return { title: '没读到可以学的内容', text: message, fixes: ['paste'] }
    case ErrorCode.PAGE_NOT_SUPPORTED:
      return { title: '这不是网页', text: message, fixes: message.includes('PDF') ? ['kb'] : [] }
    case ErrorCode.CONTENT_NOT_ALLOWED:
      return { title: '这个网页出不了题', text: message, fixes: [] }
    case ErrorCode.NETWORK:
      return { title: '网络好像断了', text: '没连上服务，检查网络后再试一次。', fixes: ['retry'] }
    default:
      return { title: '读取失败', text: message || '服务开小差了，请稍后重试。', fixes: ['retry'] }
  }
}

export const FIX_COPY: Record<WebFix, { title: string; sub: string }> = {
  retry: { title: '再读一次', sub: '网站偶尔会暂时打不开' },
  paste: { title: '粘贴要学的段落', sub: '回到首页，直接把文字贴进输入框' },
  kb: { title: '上传到我的知识库', sub: '下载这份 PDF 后上传，用资料出题' }
}

/** 网页出的题对应的网页地址（任一题出处带 url）；不是网页出题为 null */
export function webUrlOf(quiz: { questions: { sources?: { url?: string | null }[] }[] }): string | null {
  for (const q of quiz.questions) for (const s of q.sources ?? []) if (s.url) return s.url
  return null
}

/** 网页出题页地址，可带上要预填的链接 */
export const webQuizPage = (url?: string | null) =>
  url ? `/pages/web-quiz/index?url=${encodeURIComponent(url)}` : '/pages/web-quiz/index'

/** 输入框内容 → 要预览的地址：优先取其中的 http(s) 链接；没写协议但像域名（mp.weixin.qq.com/s/x）也行（后端补 https）；都不是返回 null */
export function urlTarget(raw: string): string | null {
  const url = extractUrl(raw)
  if (url) return url
  const t = (raw || '').trim()
  return /^[^\s/.]+(\.[^\s/.]+)+(\/\S*)?$/.test(t) && !/^[\d.]+$/.test(t) ? t : null
}

export const MSG_NOT_URL = '没认出网址：粘贴以 http:// 或 https:// 开头的网页链接。'
