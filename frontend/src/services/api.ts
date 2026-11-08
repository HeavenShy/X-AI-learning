import type {
  HistoryPage,
  KbDetail,
  KbDocument,
  KbList,
  KbQuizRequest,
  KnowledgeBase,
  KnowledgeTree,
  LearningStats,
  MistakeList,
  Profile,
  ProfileUpdate,
  Quiz,
  QuizDetail,
  QuizGenerateRequest,
  Report,
  ReportGenerateRequest,
  ReviewAnswerRequest,
  ReviewAnswerResult,
  StatsInsight,
  StatsRange,
  VideoJob,
  VideoQuizRequest,
  WebPreview,
  WebQuizRequest
} from '../types/api'
import { authed, authedUpload } from './auth'

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

/** 学习数据：时长分桶、题型正确率（纯统计，秒回） */
export const getLearningStats = (range: StatsRange) =>
  authed<LearningStats>('GET', `/api/v1/user/stats?range=${range}`, undefined, 15_000)

/** 图表下的一句 AI 结论：数据没变走缓存；没数据或生成失败时 insight 为 null */
export const getStatsInsight = (range: StatsRange) =>
  authed<StatsInsight>('GET', `/api/v1/user/stats/insight?range=${range}`, undefined, 45_000)

/** 知识树：已完结的话按主题分组 */
export const getKnowledgeTree = () => authed<KnowledgeTree>('GET', '/api/v1/user/knowledge-tree', undefined, 15_000)

// ---------- 知识库（都要求登录；后端没配 Embedding Key 时返回 5000） ----------

const kbPath = (kbId: string) => `/api/v1/knowledge-bases/${encodeURIComponent(kbId)}`

export const listKnowledgeBases = () => authed<KbList>('GET', '/api/v1/knowledge-bases', undefined, 15_000)

export const createKnowledgeBase = (name: string) =>
  authed<KnowledgeBase>('POST', '/api/v1/knowledge-bases', { name }, 15_000)

export const getKnowledgeBase = (kbId: string) => authed<KbDetail>('GET', kbPath(kbId), undefined, 15_000)

export const renameKnowledgeBase = (kbId: string, name: string) =>
  authed<KnowledgeBase>('PUT', kbPath(kbId), { name }, 15_000)

export const deleteKnowledgeBase = (kbId: string) => authed<null>('DELETE', kbPath(kbId), undefined, 15_000, true)

/** 上传立即返回 processing 的资料，解析与向量化在后台进行（详情页轮询状态）。20 MB 走慢网也要些时间 */
export const uploadDocument = (kbId: string, filePath: string) =>
  authedUpload<KbDocument>(`${kbPath(kbId)}/documents`, filePath, 120_000)

export const deleteDocument = (kbId: string, documentId: string) =>
  authed<null>('DELETE', `${kbPath(kbId)}/documents/${encodeURIComponent(documentId)}`, undefined, 15_000, true)

/** 只依据资料出题、不联网；同文本出题一样存为一话。检索 + 最多 3 次重试 */
export const generateKbQuiz = (kbId: string, req: KbQuizRequest) =>
  authed<Quiz>('POST', `${kbPath(kbId)}/quiz`, req, 120_000)

// ---------- 网页出题（登录可选；登录后同文本出题一样存为一话） ----------

/** 后端抓网页、提正文（必要时 Tavily 兜底），结果缓存 10 分钟，随后出题不再重复抓取 */
export const previewWebPage = (url: string) => authed<WebPreview>('POST', '/api/v1/web/preview', { url }, 30_000)

/** AI 判断主题与范围后只依据网页出题，每题带原文摘录；抓取 + 范围判断 + 最多 3 次重试 */
export const generateWebQuiz = (req: WebQuizRequest) => authed<Quiz>('POST', '/api/v1/web/quiz', req, 120_000)

// ---------- 视频出题（都要求登录；后端没配转写 Key 时返回 5000） ----------

/** 上传视频（≤200 MB）：立即返回处理中的任务，抽音轨、转文字在后台进行。大文件走慢网要给足时间 */
export const uploadVideo = (filePath: string, name: string, onProgress?: (percent: number) => void) =>
  authedUpload<VideoJob>('/api/v1/video/uploads', filePath, 600_000, { formData: { name }, onProgress })

/** B 站链接（或分享文案、BV 号）：立即返回处理中的任务 */
export const submitVideoLink = (url: string) => authed<VideoJob>('POST', '/api/v1/video/links', { url }, 30_000)

/** 解析任务状态（每 2 秒轮询一次） */
export const getVideoJob = (jobId: string) =>
  authed<VideoJob>('GET', `/api/v1/video/jobs/${encodeURIComponent(jobId)}`, undefined, 15_000)

/** 依据转好的文字稿出题，出处带时间点；范围判断 + 最多 3 次重试 */
export const generateVideoQuiz = (req: VideoQuizRequest) => authed<Quiz>('POST', '/api/v1/video/quiz', req, 120_000)
