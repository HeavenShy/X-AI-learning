/** 与后端 app/models 保持一致 */

export type QuestionType = 'single' | 'multiple' | 'judge'
export type Difficulty = 'easy' | 'medium' | 'hard'
export type DifficultyOption = 'mixed' | Difficulty
export type QuestionCount = 3 | 5 | 10

export interface Option {
  key: string
  text: string
}

/** 知识库出题的出处快照（资料删除后仍随题目保留） */
export interface QuestionSource {
  document_id: string
  document_name: string
  /** PDF 有页码；Word / TXT / Markdown 为 null */
  page: number | null
  /** 不超过 120 字的原文摘录 */
  quote: string
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
  /** 知识库出的题至少 1 项；文本出题为空数组。可选：本地存的旧闯关进度没有这个字段 */
  sources?: QuestionSource[]
}

export type SourceType = 'text' | 'knowledge_base'

export interface Quiz {
  quiz_id: string
  title: string
  summary: string
  source_type: SourceType
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
  /** 知识库：文件类型不支持 */
  FILE_TYPE_NOT_SUPPORTED: 4020,
  /** 知识库：文件为空或超过 20 MB */
  FILE_SIZE_INVALID: 4021,
  /** 知识库：超出数量上限（知识库 10 个 / 资料 50 份） */
  LIMIT_EXCEEDED: 4022,
  /** 知识库：所选资料都还没准备好 */
  NO_READY_DOCUMENTS: 4023,
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

// ---------- 错题本（backend/app/models/review.py） ----------

export interface MistakeItem {
  quiz_id: string
  /** 所属话的标题（列表分组标题） */
  quiz_title: string
  /** 完整题目（含答案与讲解）：重做时本地判题播动画，掌握状态以服务端为准 */
  question: Question
  /** 上次的错误答案（未作答为空数组） */
  last_selected_answers: string[]
  /** 累计答错次数（闯关那次算 1） */
  wrong_count: number
  /** 首次答错时间，ISO 8601 UTC */
  first_wrong_at: string
}

export interface MistakeList {
  items: MistakeItem[]
  total: number
}

export interface ReviewAnswerRequest {
  quiz_id: string
  question_id: string
  selected_answers: string[]
}

export interface ReviewAnswerResult {
  is_correct: boolean
  correct_answers: string[]
  /** 提交后是否已掌握（已移出错题本） */
  mastered: boolean
}

// ---------- 知识库（backend/app/models/kb.py） ----------

export type DocumentStatus = 'processing' | 'ready' | 'failed'
export type KbFileType = 'pdf' | 'docx' | 'txt' | 'md'

export interface KnowledgeBase {
  kb_id: string
  name: string
  document_count: number
  /** 可出题（ready）的资料数 */
  ready_count: number
  /** ISO 8601 UTC */
  created_at: string
  updated_at: string
}

export interface KbList {
  items: KnowledgeBase[]
  total: number
  /** 所有知识库合计的资料数与上限 */
  document_total: number
  document_limit: number
}

export interface KbDocument {
  document_id: string
  filename: string
  file_type: KbFileType
  size_bytes: number
  status: DocumentStatus
  /** 仅失败时有 */
  fail_reason: string | null
  /** 仅 PDF 有 */
  page_count: number | null
  char_count: number
  /** 上传时间，ISO 8601 UTC */
  created_at: string
}

export interface KbDetail {
  knowledge_base: KnowledgeBase
  documents: KbDocument[]
}

export interface KbQuizRequest {
  /** 为空：该库全部资料 */
  document_ids: string[]
  /** 想重点学什么（选填，≤200 字） */
  focus: string
  question_count: QuestionCount
  difficulty: DifficultyOption
}

