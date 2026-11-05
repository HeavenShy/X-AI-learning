/** 错题本（复习页）：按话分组、答错次数文案 */

import type { MistakeItem, Question } from '../types/api'

export interface MistakeGroup {
  quizId: string
  title: string
  /** 组内题数（组标题“共 N 题”） */
  count: number
  items: MistakeItem[]
}

/** 按 quiz_id 分组：组按首次出现的顺序，组内保持接口顺序（接口已按完结时间新到旧、话内按题序） */
export function groupMistakes(items: MistakeItem[]): MistakeGroup[] {
  const groups = new Map<string, MistakeGroup>()
  for (const item of items) {
    let g = groups.get(item.quiz_id)
    if (!g) {
      g = { quizId: item.quiz_id, title: item.quiz_title, count: 0, items: [] }
      groups.set(item.quiz_id, g)
    }
    g.items.push(item)
    g.count += 1
  }
  return Array.from(groups.values())
}

export const wrongCountLabel = (n: number) => `错 ${n} 次`

export interface MistakeKey {
  quiz_id: string
  question_id: string
}

/** 错题的身份：question_id 只在一话内唯一 */
export const sameMistake = (item: MistakeItem, key: MistakeKey) =>
  item.quiz_id === key.quiz_id && item.question.id === key.question_id

/** 重做答对返回复习页时，先在本地去掉那一条，免得重新拉列表前闪一下 */
export const withoutMistake = (items: MistakeItem[], key: MistakeKey) => items.filter((i) => !sameMistake(i, key))

/** 重做页“上次的答案”：判断题显示“对 / 错”，其余显示选项字母；未作答单独说明 */
export function lastAnswerText(q: Question, selected: string[]): string {
  if (selected.length === 0) return '上次没作答'
  if (q.type === 'judge') {
    const text = q.options.find((o) => o.key === selected[0])?.text ?? selected[0]
    return `上次选了“${text}”`
  }
  return `上次选了 ${selected.join('、')}`
}
