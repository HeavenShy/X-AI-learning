import type {
  HistoryPage,
  MistakeList,
  Profile,
  ProfileUpdate,
  Quiz,
  QuizDetail,
  QuizGenerateRequest,
  Report,
  ReportGenerateRequest,
  ReviewAnswerRequest,
  ReviewAnswerResult
} from '../types/api'
import { authed } from './auth'

/** 后端最多重试 3 次，每次 LLM 超时 60s；实际一般 5–12 秒。登录后题库会保存到“历史记录” */
export const generateQuiz = (req: QuizGenerateRequest) => authed<Quiz>('POST', '/api/v1/quiz/generate', req, 120_000)

/** 登录后答题记录、经验金币、报告都会落库（同一话只结算一次） */
export const generateReport = (req: ReportGenerateRequest) =>
  authed<Report>('POST', '/api/v1/report/generate', req, 90_000)

export const getProfile = () => authed<Profile>('GET', '/api/v1/user/profile', undefined, 15_000)

export const updateProfile = (req: ProfileUpdate) => authed<Profile>('PUT', '/api/v1/user/profile', req, 15_000)

export const listQuizzes = (page: number, pageSize = 20) =>
  authed<HistoryPage>('GET', `/api/v1/user/quizzes?page=${page}&page_size=${pageSize}`, undefined, 15_000)

export const getQuizDetail = (quizId: string) =>
  authed<QuizDetail>('GET', `/api/v1/user/quizzes/${encodeURIComponent(quizId)}`, undefined, 15_000)

/** 当前用户还没掌握的错题：按话完结时间新到旧，话内按题序 */
export const listMistakes = () => authed<MistakeList>('GET', '/api/v1/review/mistakes', undefined, 15_000)

/** 重做一道错题：服务端按存档答案判题，答对即移出错题本；不发经验金币 */
export const submitReviewAnswer = (req: ReviewAnswerRequest) =>
  authed<ReviewAnswerResult>('POST', '/api/v1/review/answer', req, 15_000)
