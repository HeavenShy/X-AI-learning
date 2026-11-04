/**
 * 全局状态（Zustand）。
 * - profile / draft / session 持久化到本地 Storage（MVP 无账号体系）
 * - 生成中的请求参数、待开始的题库、报告放内存
 */

import Taro from '@tarojs/taro'
import { create } from 'zustand'

import { advance, answerCurrent, createSession, sessionStats, type Session } from '../core/session'
import type { DifficultyOption, Quiz, QuestionCount, Report } from '../types/api'

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

export interface GenRequest {
  text: string
  count: QuestionCount
  difficulty: DifficultyOption
}

export interface ReportState {
  quizId: string
  status: 'loading' | 'done' | 'error'
  data: Report | null
}

interface State {
  profile: Profile
  draft: Draft
  session: Session | null
  genRequest: GenRequest | null
  pendingQuiz: Quiz | null
  /** 出题页带回首页、显示在输入框下方的错误（如内容不合规） */
  homeError: string | null
  report: ReportState | null

  setDraft: (d: Partial<Draft>) => void
  setHomeError: (msg: string | null) => void
  requestGenerate: (req: GenRequest) => void
  setPendingQuiz: (q: Quiz | null) => void
  startSession: () => void
  answer: (selected: string[], durationMs: number) => void
  next: () => void
  settleReward: () => void
  setReport: (r: ReportState | null) => void
}

const KEYS = { profile: 'yhyd.profile', draft: 'yhyd.draft', session: 'yhyd.session' } as const

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
  draft: load<Draft>(KEYS.draft, { text: '', count: 5 }),
  session: load<Session | null>(KEYS.session, null),
  genRequest: null,
  pendingQuiz: null,
  homeError: null,
  report: null,

  setDraft: (d) => set({ draft: { ...get().draft, ...d } }),
  setHomeError: (homeError) => set({ homeError }),
  requestGenerate: (genRequest) => set({ genRequest, pendingQuiz: null, homeError: null }),
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

  setReport: (report) => set({ report })
}))

// 持久化：对应字段变化时写入 Storage
useStore.subscribe((state, prev) => {
  if (state.profile !== prev.profile) save(KEYS.profile, state.profile)
  if (state.draft !== prev.draft) save(KEYS.draft, state.draft)
  if (state.session !== prev.session) save(KEYS.session, state.session)
})
