/** 学习数据 / 知识树页的纯逻辑：柱高、对比文案、掌握度着色、“再闯一轮”的出题输入 */

import type { StatsBar, StatsRange, TreeQuiz, TypeAccuracy } from '../types/api'
import { INPUT_MAX_CHARS, INPUT_MIN_CHARS, visibleLength } from './format'
import { MASTERED_FROM, WEAK_BELOW } from './mastery'

export const RANGE_OPTIONS: { key: StatsRange; label: string }[] = [
  { key: 'week', label: '本周' },
  { key: 'month', label: '本月' },
  { key: 'all', label: '全部' }
]

/** 有时长的柱子最矮也露一点，免得看起来像 0 */
const MIN_BAR_PERCENT = 4

/** 每根柱子的高度（占最高那根的百分比）；全是 0 时都为 0 */
export function barHeights(bars: StatsBar[]): number[] {
  const max = Math.max(0, ...bars.map((b) => b.minutes))
  if (max === 0) return bars.map(() => 0)
  return bars.map((b) => (b.minutes === 0 ? 0 : Math.max(MIN_BAR_PERCENT, Math.round((b.minutes / max) * 100))))
}

const PREV_NAME: Record<StatsRange, string> = { week: '上周', month: '上月', all: '' }

/** 大数字后面的小字：“分钟，比上周多 12 分钟”；全部时只有“分钟” */
export function compareText(range: StatsRange, total: number, prev: number | null): string {
  if (prev === null || range === 'all') return '分钟'
  const diff = total - prev
  const name = PREV_NAME[range]
  if (diff > 0) return `分钟，比${name}多 ${diff} 分钟`
  if (diff < 0) return `分钟，比${name}少 ${-diff} 分钟`
  return `分钟，和${name}一样`
}

export type MasteryClass = 'g' | 'y' | 'r'

/** 掌握度着色：≥80 绿、60–79 黄、<60 红（与报告页一致） */
export function masteryClass(accuracy: number): MasteryClass {
  if (accuracy >= MASTERED_FROM) return 'g'
  if (accuracy < WEAK_BELOW) return 'r'
  return 'y'
}

/** 题型正确率进度条标红：做过且低于 60% */
export const isWeakType = (t: TypeAccuracy) => t.total > 0 && t.accuracy < WEAK_BELOW

/** 知识树里红色的话可以“再闯一轮” */
export const canRetry = (q: TreeQuiz) => masteryClass(q.accuracy) === 'r'

/**
 * “再闯一轮”的出题输入：优先“标题：重点练 答错的知识点”；没有答错知识点时用原来的输入，
 * 原输入太短（知识库出题可能没填重点）就用“标题：再出一组题”。
 */
export function retryInput(q: TreeQuiz): string {
  let text: string
  if (q.weak_points.length > 0) text = `${q.title}：重点练 ${q.weak_points.join('、')}`
  else if (visibleLength(q.user_input) >= INPUT_MIN_CHARS) text = q.user_input
  else text = `${q.title}：再出一组题`
  return Array.from(text).slice(0, INPUT_MAX_CHARS).join('')
}
