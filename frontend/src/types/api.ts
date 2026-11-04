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
  INTERNAL_ERROR: 5000,
  /** 前端自定义：网络不通 / 超时 */
  NETWORK: -1,
  /** 前端自定义：用户取消 */
  ABORTED: -2
} as const
