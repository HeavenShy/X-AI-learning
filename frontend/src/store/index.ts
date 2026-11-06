/**
 * 全局状态（Zustand）。
 * - profile / me / draft / session 持久化到本地 Storage
 * - 登录后 profile（经验、金币、话数）以后端为准：启动、回到首页 / 我的、报告生成后从 /user/profile 同步；
 *   结算页仍按同一规则先在本地算出来，动画不用等接口。未登录（登录失败）时就是纯本地数据。
 * - 生成中的请求参数、待开始的题库、报告、海报数据、正在重做的错题放内存
 */

import Taro from '@tarojs/taro'
import { create } from 'zustand'

import { advance, answerCurrent, createSession, sessionStats, type Session } from '../core/session'
import type { MistakeKey } from '../core/review'
import type { PosterData } from '../services/poster'
import type {
  DifficultyOption,
  MistakeItem,
  Profile as ServerProfile,
  Quiz,
  QuestionCount,
  Report,
  UserBrief
} from '../types/api'

export interface Profile {
  xp: number
  coins: number
  /** 已完结的话数（海报“我的第 N 话”） */
  episodes: number
}

export interface Draft {
  text: string
  count: QuestionCount
}

/** 用知识库出题时的资料范围；documentIds 为空表示整个库 */
export interface KbGenRequest {
  kbId: string
  kbName: string
  documentIds: string[]
}

export interface GenRequest {
  /** 文本出题：学习内容；知识库出题：想重点学什么（可为空） */
  text: string
  count: QuestionCount
  difficulty: DifficultyOption
  kb?: KbGenRequest
}

export interface ReportState {
  quizId: string
  status: 'loading' | 'done' | 'error'
  data: Report | null
}

interface State {
  profile: Profile
  /** 后端用户资料（登录后才有） */
  me: ServerProfile | null
  /** 海报页要画的内容：报告页（本次或历史）进入海报前写入 */
  poster: PosterData | null
  draft: Draft
  session: Session | null
  genRequest: GenRequest | null
  pendingQuiz: Quiz | null
  /** 出题页带回首页、显示在输入框下方的错误（如内容不合规） */
  homeError: string | null
  /** 知识库出题失败（资料未就绪 4023 / 重点不合规 4003）带回出题设置页的提示 */
  kbError: string | null
  report: ReportState | null
  /** 复习页点开、正在重做的错题（不持久化：被系统回收后重做页回到复习页） */
  reviewing: MistakeItem | null
  /** 重做页刚答对、服务端已标为掌握的错题：复习页回来时先在本地去掉，再重新拉列表 */
  reviewMastered: MistakeKey | null

  setDraft: (d: Partial<Draft>) => void
  setHomeError: (msg: string | null) => void
  setKbError: (msg: string | null) => void
  requestGenerate: (req: GenRequest) => void
  setPendingQuiz: (q: Quiz | null) => void
  startSession: () => void
  answer: (selected: string[], durationMs: number) => void
  next: () => void
  settleReward: () => void
  setReport: (r: ReportState | null) => void
  applyLogin: (u: UserBrief) => void
  applyProfile: (p: ServerProfile) => void
  setPoster: (p: PosterData | null) => void
  setReviewing: (item: MistakeItem | null) => void
  setReviewMastered: (key: MistakeKey | null) => void
}

const KEYS = { profile: 'yhyd.profile', me: 'yhyd.me', draft: 'yhyd.draft', session: 'yhyd.session' } as const

function load<T>(key: string, fallback: T): T {
  try {
    const v = Taro.getStorageSync(key)
    return v ? (v as T) : fallback
  } catch {
    return fallback
  }
}

function save(key: string, value: unknown) {
  try {
    if (value == null) Taro.removeStorageSync(key)
    else Taro.setStorageSync(key, value)
  } catch (e) {
    console.warn('[store] 保存失败', key, e)
  }
}

export const useStore = create<State>((set, get) => ({
  profile: load<Profile>(KEYS.profile, { xp: 0, coins: 0, episodes: 0 }),
  me: load<ServerProfile | null>(KEYS.me, null),
  poster: null,
  draft: load<Draft>(KEYS.draft, { text: '', count: 5 }),
  session: load<Session | null>(KEYS.session, null),
  genRequest: null,
  pendingQuiz: null,
  homeError: null,
  kbError: null,
  report: null,
  reviewing: null,
  reviewMastered: null,

  setDraft: (d) => set({ draft: { ...get().draft, ...d } }),
  setHomeError: (homeError) => set({ homeError }),
  setKbError: (kbError) => set({ kbError }),
  requestGenerate: (genRequest) => set({ genRequest, pendingQuiz: null, homeError: null, kbError: null }),
  setPendingQuiz: (pendingQuiz) => set({ pendingQuiz }),

  startSession: () => {
    const { pendingQuiz, genRequest } = get()
    if (!pendingQuiz) return
    set({ session: createSession(pendingQuiz, genRequest?.difficulty ?? 'mixed', Date.now()), report: null })
  },

  answer: (selected, durationMs) => {
    const s = get().session
    if (s) set({ session: answerCurrent(s, selected, durationMs, Date.now()) })
  },

  next: () => {
    const s = get().session
    if (s) set({ session: advance(s, Date.now()) })
  },

  /** 通关时把本话经验金币结算进个人资料（只结算一次） */
  settleReward: () => {
    const { session, profile } = get()
    if (!session || !session.finished || session.rewarded) return
    const st = sessionStats(session)
    const episode = profile.episodes + 1
    set({
      profile: { xp: profile.xp + st.xp, coins: profile.coins + st.coins, episodes: episode },
      session: { ...session, rewarded: true, reward: { xpBefore: profile.xp, xp: st.xp, coins: st.coins, episode } }
    })
  },

  setReport: (report) => set({ report }),

  /** 登录接口只返回基础资料：先更新经验金币，统计数据等 applyProfile */
  applyLogin: (u) => {
    const { me, profile } = get()
    set({
      profile: { ...profile, xp: u.total_xp, coins: u.total_coins },
      me: me && me.id === u.id ? { ...me, ...u } : null
    })
  },

  applyProfile: (p) => set({ me: p, profile: { xp: p.total_xp, coins: p.total_coins, episodes: p.quiz_count } }),

  setPoster: (poster) => set({ poster }),
  setReviewing: (reviewing) => set({ reviewing }),
  setReviewMastered: (reviewMastered) => set({ reviewMastered })
}))

// 持久化：对应字段变化时写入 Storage
useStore.subscribe((state, prev) => {
  if (state.profile !== prev.profile) save(KEYS.profile, state.profile)
  if (state.me !== prev.me) save(KEYS.me, state.me)
  if (state.draft !== prev.draft) save(KEYS.draft, state.draft)
  if (state.session !== prev.session) save(KEYS.session, state.session)
})
