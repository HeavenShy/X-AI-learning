/** 本地即时判题 */

import type { Question } from '../types/api'

export interface JudgeResult {
  isCorrect: boolean
  picked: string[]
  correct: string[]
  wrongPicked: string[]
  missed: string[]
}

const norm = (keys: string[]) => Array.from(new Set(keys.map((k) => k.trim().toUpperCase()))).sort()

export function judgeAnswer(q: Question, selected: string[]): JudgeResult {
  const picked = norm(selected)
  const correct = norm(q.answer)
  const wrongPicked = picked.filter((k) => !correct.includes(k))
  const missed = correct.filter((k) => !picked.includes(k))
  return { isCorrect: picked.length > 0 && wrongPicked.length === 0 && missed.length === 0, picked, correct, wrongPicked, missed }
}

export type OptionState = 'right' | 'wrong' | 'missed' | 'dim'

/**
 * 选项判题后的样式与动画顺序（原型：先标错 m1、再标对 m2、再提示漏选 m3）。
 * order=0 表示没有标记。
 */
export function optionVisual(q: Question, r: JudgeResult, key: string): { state: OptionState; order: number } {
  const hasWrong = r.wrongPicked.length > 0
  if (r.wrongPicked.includes(key)) return { state: 'wrong', order: 1 }
  if (r.correct.includes(key)) {
    if (r.picked.includes(key)) return { state: 'right', order: hasWrong ? 2 : 1 }
    // 没选到的正确项：多选题标“漏选”，单选/判断直接亮出正确答案
    if (q.type === 'multiple') return { state: 'missed', order: 3 }
    return { state: 'right', order: 2 }
  }
  return { state: 'dim', order: 0 }
}

export function resultTitle(q: Question, r: JudgeResult): string {
  if (r.isCorrect) return '答对了'
  if (q.type === 'multiple') {
    return r.missed.length > 0 ? `差一点，漏了 ${r.missed.join('、')}` : `多选了 ${r.wrongPicked.join('、')}`
  }
  if (q.type === 'judge') return `答错了，这个说法${r.correct[0] === 'A' ? '是对的' : '不对'}`
  return `答错了，正确答案是 ${r.correct[0]}`
}

export function answerLine(q: Question): string {
  if (q.type === 'judge') {
    const text = q.options.find((o) => o.key === q.answer[0])?.text ?? q.answer[0]
    return `正确答案：${text}`
  }
  return `正确答案：${norm(q.answer).join('、')}`
}
