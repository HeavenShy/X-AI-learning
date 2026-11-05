/** 一次闯关（一话）的会话状态：纯函数，便于持久化与续答 */

import type { AnswerRecord, DifficultyOption, Question, Quiz } from '../types/api'
import { judgeAnswer } from './judge'
import { COINS_PER_CORRECT, XP_PER_CORRECT } from './level'

export interface AnswerState {
  selected: string[]
  isCorrect: boolean
  durationMs: number
}

export interface Session {
  quiz: Quiz
  difficulty: DifficultyOption
  index: number
  answers: Record<string, AnswerState>
  startedAt: number
  updatedAt: number
  finished: boolean
  /** 经验金币是否已结算进个人资料，防止重复结算 */
  rewarded: boolean
  /** 结算时的经验快照，用于结算页 / 报告页重复展示 */
  reward?: { xpBefore: number; xp: number; coins: number; episode: number }
}

export type CellState = 'ok' | 'no' | 'now' | ''

export function createSession(quiz: Quiz, difficulty: DifficultyOption, now: number): Session {
  return { quiz, difficulty, index: 0, answers: {}, startedAt: now, updatedAt: now, finished: false, rewarded: false }
}

export const currentQuestion = (s: Session): Question => s.quiz.questions[s.index]
export const currentAnswer = (s: Session): AnswerState | undefined => s.answers[currentQuestion(s).id]
export const isLastQuestion = (s: Session) => s.index >= s.quiz.questions.length - 1

export function answerCurrent(s: Session, selected: string[], durationMs: number, now: number): Session {
  const q = currentQuestion(s)
  if (s.answers[q.id]) return s
  const { isCorrect, picked } = judgeAnswer(q, selected)
  return {
    ...s,
    answers: { ...s.answers, [q.id]: { selected: picked, isCorrect, durationMs: Math.max(0, Math.round(durationMs)) } },
    updatedAt: now
  }
}

export function advance(s: Session, now: number): Session {
  if (!currentAnswer(s)) return s
  if (isLastQuestion(s)) return { ...s, finished: true, updatedAt: now }
  return { ...s, index: s.index + 1, updatedAt: now }
}

export function cellStates(s: Session): CellState[] {
  return s.quiz.questions.map((q, i) => {
    const a = s.answers[q.id]
    if (a) return a.isCorrect ? 'ok' : 'no'
    return i === s.index && !s.finished ? 'now' : ''
  })
}

export interface SessionStats {
  correct: number
  total: number
  answered: number
  accuracy: number
  durationMs: number
  xp: number
  coins: number
}

export function sessionStats(s: Session): SessionStats {
  const answers = Object.values(s.answers)
  const correct = answers.filter((a) => a.isCorrect).length
  const total = s.quiz.questions.length
  return {
    correct,
    total,
    answered: answers.length,
    accuracy: total ? Math.round((correct * 100) / total) : 0,
    durationMs: answers.reduce((sum, a) => sum + a.durationMs, 0),
    xp: correct * XP_PER_CORRECT,
    coins: correct * COINS_PER_CORRECT
  }
}

export function toAnswerRecords(s: Session): AnswerRecord[] {
  return s.quiz.questions
    .filter((q) => s.answers[q.id])
    .map((q) => {
      const a = s.answers[q.id]
      return { question_id: q.id, selected_answers: a.selected, is_correct: a.isCorrect, duration_ms: a.durationMs }
    })
}

export const resumeTitle = (s: Session) => `${s.quiz.title}，看到第 ${s.index + 1} 格`
