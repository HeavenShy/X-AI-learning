/**
 * 本话复盘报告的生成：结算页一进入就在后台发起（登录后同时落库答题记录、结算经验），
 * 报告页复用同一份结果；失败时报告页点“重试”再发。
 */

import { toAnswerRecords } from '../core/session'
import { useStore } from '../store'
import { refreshProfile } from './account'
import { generateReport } from './api'

export function ensureReport(force = false): void {
  const { session: s, report: r, setReport } = useStore.getState()
  if (!s || !s.finished) return
  const quizId = s.quiz.quiz_id
  if (!force && r && r.quizId === quizId && r.status !== 'error') return
  setReport({ quizId, status: 'loading', data: null })
  generateReport({
    quiz_id: quizId,
    topic: s.quiz.title,
    questions: s.quiz.questions,
    answer_records: toAnswerRecords(s)
  })
    .promise.then((data) => setReport({ quizId, status: 'done', data }))
    .catch(() => setReport({ quizId, status: 'error', data: null }))
    // 不论 AI 复盘成没成，登录用户的成绩和经验都已保存，同步一下
    .finally(() => void refreshProfile())
}
