/** 与后端 app/models 保持一致 */

export type QuestionType = 'single' | 'multiple' | 'judge'
export type Difficulty = 'easy' | 'medium' | 'hard'
export type DifficultyOption = 'mixed' | Difficulty
export type QuestionCount = 3 | 5 | 10

export interface Option {
  key: string
  text: string
}

export interface Question {
  id: string
  type: QuestionType
  stem: string
  options: Option[]
  answer: string[]
  explanation: string
  knowledge_point: string
  difficulty: Difficulty
}

export interface Quiz {
  quiz_id: string
  title: string
  summary: string
  source_type: 'text'
  user_input: string
  questions: Question[]
}

export interface QuizGenerateRequest {
  user_input: string
  question_count: QuestionCount
  difficulty: DifficultyOption
}

export interface AnswerRecord {
  question_id: string
  selected_answers: string[]
  is_correct: boolean
  duration_ms: number
}

export interface ReportGenerateRequest {
  quiz_id: string
  topic: string
  questions: Question[]
  answer_records: AnswerRecord[]
}

export interface KnowledgeMastery {
  point: string
  correct: number
  total: number
  accuracy: number
}

export interface Report {
  accuracy: number
  correct_count: number
  total_count: number
  total_duration_ms: number
  mastered_points: string[]
  weak_points: string[]
  knowledge_mastery: KnowledgeMastery[]
  three_line_summary: string[]
  advice: string[]
  share_quote: string
}

export interface ApiEnvelope<T> {
  code: number
  message: string
  data: T | null
}

/** 后端错误码，见 backend/README.md */
export const ErrorCode = {
  OK: 0,
  INVALID_PARAMS: 4000,
  QUIZ_GENERATE_FAILED: 4001,
  INPUT_TOO_SHORT: 4002,
  CONTENT_NOT_ALLOWED: 4003,
  REPORT_GENERATE_FAILED: 4004,
  UNAUTHORIZED: 4010,
  LOGIN_FAILED: 4011,
  NICKNAME_NOT_ALLOWED: 4012,
  NOT_FOUND: 4040,
  INTERNAL_ERROR: 5000,
  /** 前端自定义：网络不通 / 超时 */
  NETWORK: -1,
  /** 前端自定义：用户取消 */
  ABORTED: -2
} as const

// ---------- 用户系统（backend/app/models/user.py） ----------

export interface UserBrief {
  id: number
  nickname: string
  avatar_url: string
  total_xp: number
  total_coins: number
}

export interface LoginResponse {
  token: string
  user: UserBrief
}

export interface Profile extends UserBrief {
  /** 已学话数 */
  quiz_count: number
  correct_count: number
  question_count: number
  /** 总正确率（整数百分比） */
  average_accuracy: number
  week_minutes: number
}

export interface ProfileUpdate {
  nickname?: string
  avatar_url?: string
}

export interface HistoryItem {
  quiz_id: string
  title: string
  question_count: number
  correct_count: number
  accuracy: number
  total_duration_ms: number
  has_report: boolean
  /** ISO 8601 UTC，如 2026-11-05T02:03:04Z */
  created_at: string
}

export interface HistoryPage {
  items: HistoryItem[]
  total: number
  page: number
  page_size: number
}

export interface QuizDetail {
  quiz: Quiz
  difficulty: DifficultyOption
  answer_records: AnswerRecord[]
  accuracy: number
  correct_count: number
  total_count: number
  total_duration_ms: number
  reward: { xp: number; coins: number }
  report: Report | null
  episode: number
  created_at: string
}
