import type { Quiz, QuizGenerateRequest, Report, ReportGenerateRequest } from '../types/api'
import { post } from './request'

/** 后端最多重试 3 次，每次 LLM 超时 60s；实际一般 5–12 秒 */
export const generateQuiz = (req: QuizGenerateRequest) => post<Quiz>('/api/v1/quiz/generate', req, 120_000)

export const generateReport = (req: ReportGenerateRequest) => post<Report>('/api/v1/report/generate', req, 90_000)
