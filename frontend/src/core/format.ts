import type { DifficultyOption, QuestionCount, QuestionType } from '../types/api'

export const INPUT_MIN_CHARS = 4
export const INPUT_MAX_CHARS = 2000
export const MSG_TOO_SHORT = '内容太短，AI 猜不出你想学哪方面。至少写 4 个字，比如“RAG 是怎么工作的”。'

export const TYPE_LABEL: Record<QuestionType, string> = { single: '单选', multiple: '多选', judge: '判断' }

export const DIFFICULTY_LABEL: Record<DifficultyOption, string> = {
  mixed: '难度混合',
  easy: '难度简单',
  medium: '难度中等',
  hard: '难度较难'
}

const PLANS: Record<QuestionCount, [number, number, number]> = { 3: [1, 1, 1], 5: [3, 1, 1], 10: [6, 2, 2] }
const MINUTES: Record<QuestionCount, number> = { 3: 2, 5: 4, 10: 8 }

export const estimateMinutes = (count: QuestionCount) => MINUTES[count]

export function planText(count: QuestionCount): string {
  const [s, m, j] = PLANS[count]
  return `单选 ${s}、多选 ${m}、判断 ${j}`
}

export function visibleLength(text: string): number {
  return Array.from(text).filter((ch) => !/\s/.test(ch)).length
}

/** 本地输入校验，返回错误文案或 null */
export function validateInput(text: string): string | null {
  if (visibleLength(text) < INPUT_MIN_CHARS) return MSG_TOO_SHORT
  return null
}

export function formatDuration(ms: number): string {
  const total = Math.round(ms / 1000)
  const m = Math.floor(total / 60)
  const s = total % 60
  return m > 0 ? `${m} 分 ${s} 秒` : `${s} 秒`
}

const pad = (n: number) => String(n).padStart(2, '0')

export function formatInterrupted(ts: number, now: number): string {
  const d = new Date(ts)
  const today = new Date(now)
  today.setHours(0, 0, 0, 0)
  const dayDiff = Math.round((today.getTime() - new Date(d).setHours(0, 0, 0, 0)) / 86_400_000)
  const time = `${pad(d.getHours())}:${pad(d.getMinutes())}`
  if (dayDiff === 0) return `今天 ${time} 中断`
  if (dayDiff === 1) return `昨天 ${time} 中断`
  return `${d.getMonth() + 1} 月 ${d.getDate()} 日 ${time} 中断`
}

const TOPIC_PREFIXES = ['我想学习', '我想了解', '我想知道', '我想学', '想学习', '想了解', '想学']

/** 出题中页面“你想学：xxx”的展示文案 */
export function displayTopic(input: string): string {
  let t = input.trim()
  const prefix = TOPIC_PREFIXES.find((p) => t.startsWith(p))
  if (prefix) t = t.slice(prefix.length)
  return t.replace(/[。.!！?？\s]+$/u, '')
}

/** 秒 → mm:ss（满 1 小时为 h:mm:ss），视频时间点用 */
export function formatClock(seconds: number): string {
  const total = Math.max(0, Math.floor(seconds))
  const h = Math.floor(total / 3600)
  const m = Math.floor((total % 3600) / 60)
  const s = total % 60
  return h ? `${h}:${pad(m)}:${pad(s)}` : `${pad(m)}:${pad(s)}`
}
