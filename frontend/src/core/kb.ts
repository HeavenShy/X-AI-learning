/**
 * 知识库的纯逻辑（原型 02 第 7、9、10、12 屏）：上传前预检、状态与出处文案、出题设置默认勾选。
 * 预检与后端同规则（扩展名、20 MB、非空），只为少传无效文件；最终以后端判断为准（后端还会检查文件内容）。
 */

import type { DocumentStatus, KbDocument, KnowledgeBase, QuestionSource } from '../types/api'

export const KB_EXTENSIONS = ['pdf', 'docx', 'txt', 'md'] as const
export const KB_MAX_FILE_BYTES = 20 * 1024 * 1024
export const KB_NAME_MAX = 20
export const KB_FOCUS_MAX = 200
/** 有资料处理中时详情页的刷新间隔 */
export const KB_POLL_MS = 3000

export const MSG_TYPE_NOT_SUPPORTED = '只支持 PDF（文字版）、Word（.docx）、TXT、Markdown 文件'
export const MSG_FILE_EMPTY = '文件是空的，换一个试试'
export const MSG_FILE_TOO_LARGE = '文件不能超过 20 MB'

export function fileExtension(name: string): string {
  const i = name.lastIndexOf('.')
  return i >= 0 ? name.slice(i + 1).toLowerCase() : ''
}

/** 上传前预检，返回错误文案或 null */
export function precheckFile(file: { name: string; size: number }): string | null {
  if (!(KB_EXTENSIONS as readonly string[]).includes(fileExtension(file.name))) return MSG_TYPE_NOT_SUPPORTED
  if (file.size <= 0) return MSG_FILE_EMPTY
  if (file.size > KB_MAX_FILE_BYTES) return MSG_FILE_TOO_LARGE
  return null
}

const normalizeName = (s: string) => s.trim().split(/\s+/).filter(Boolean).join(' ')

/** 知识库名称：与后端同规则（去首尾空白、压缩空白，1–20 字） */
export function validateKbName(raw: string): string | null {
  const n = normalizeName(raw)
  if (!n) return '知识库名称不能为空'
  if (Array.from(n).length > KB_NAME_MAX) return `知识库名称最多 ${KB_NAME_MAX} 个字`
  return null
}

export const cleanKbName = normalizeName

export const STATUS_LABEL: Record<DocumentStatus, string> = { processing: '处理中', ready: '可出题', failed: '失败' }
/** 原型 .pill 的颜色：run 黄 / ok 绿 / no 红 */
export const STATUS_PILL: Record<DocumentStatus, string> = { processing: 'run', ready: 'ok', failed: 'no' }

export function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function formatChars(n: number): string {
  return n >= 10000 ? `${(n / 10000).toFixed(1).replace(/\.0$/, '')} 万字` : `${n} 字`
}

/** 资料列表第二行：处理中给提示，可出题给页数 / 字数，失败给原因 */
export function documentSubline(doc: KbDocument): string {
  if (doc.status === 'processing') return '正在提取文字，一般不到一分钟'
  if (doc.status === 'failed') return doc.fail_reason || '处理失败，请删除后重新上传'
  const parts = [doc.page_count != null ? `${doc.page_count} 页` : '', formatChars(doc.char_count)].filter(Boolean)
  return parts.join('，')
}

/** 讲解里的出处行：出处：文件名，第 N 页（没有页码只显示文件名） */
export function formatSource(src: QuestionSource): string {
  return src.page != null ? `出处：${src.document_name}，第 ${src.page} 页` : `出处：${src.document_name}`
}

export const hasProcessing = (docs: KbDocument[]) => docs.some((d) => d.status === 'processing')

export const readyDocuments = (docs: KbDocument[]) => docs.filter((d) => d.status === 'ready')

/** 出题设置默认勾选全部可出题资料 */
export const defaultSelection = (docs: KbDocument[]) => readyDocuments(docs).map((d) => d.document_id)

/** 切换勾选：只有可出题的资料能勾 */
export function toggleSelection(selected: string[], doc: KbDocument): string[] {
  if (doc.status !== 'ready') return selected
  return selected.includes(doc.document_id)
    ? selected.filter((id) => id !== doc.document_id)
    : [...selected, doc.document_id]
}

/**
 * 发给后端的 document_ids：勾选了全部可出题资料时传空数组（= 整个库，之后新处理好的资料也算进来），
 * 否则传勾选的 id（按资料列表顺序）。
 */
export function selectedIds(docs: KbDocument[], selected: string[]): string[] {
  const ready = defaultSelection(docs)
  const picked = ready.filter((id) => selected.includes(id))
  return picked.length === ready.length ? [] : picked
}

const startOfDay = (ts: number) => new Date(ts).setHours(0, 0, 0, 0)

/** 原型 02 第 7 屏：今天更新 / 昨天更新 / 3 天前更新 / 11 月 2 日更新 */
export function updatedLabel(iso: string, now: number): string {
  const ts = Date.parse(iso)
  const diff = Math.round((startOfDay(now) - startOfDay(ts)) / 86_400_000)
  if (diff <= 0) return '今天更新'
  if (diff === 1) return '昨天更新'
  if (diff < 7) return `${diff} 天前更新`
  const d = new Date(ts)
  return `${d.getMonth() + 1} 月 ${d.getDate()} 日更新`
}

export function kbSubline(kb: KnowledgeBase, now: number): string {
  const count = kb.document_count ? `${kb.document_count} 份资料` : '还没有资料'
  return `${count}，${updatedLabel(kb.updated_at, now)}`
}

/** 资料用量条的百分比（0–100） */
export function quotaPercent(total: number, limit: number): number {
  if (limit <= 0) return 0
  return Math.min(100, Math.round((total / limit) * 100))
}

/** 列表 / 详情加载失败时的空状态文案：后端没开知识库（5000）与网络不通分开说 */
export function loadErrorCopy(code: number | null): { title: string; text: string } {
  if (code === 5000) return { title: '知识库暂时不可用', text: '服务还没开通知识库功能，先用一句话出题吧。' }
  if (code === 4040) return { title: '没找到这个知识库', text: '它可能已经被删除了。' }
  return { title: '没连上服务', text: '网络好像断了，检查一下再试。' }
}
