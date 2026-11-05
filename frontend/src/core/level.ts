/** 等级与经验。称号来自设计规范：路人 → 龙套 → 配角 → 主角 → 传说 */

export const XP_PER_CORRECT = 10
export const COINS_PER_CORRECT = 5

interface LevelDef {
  lv: number
  name: string
  min: number
}

const LEVELS: LevelDef[] = [
  { lv: 1, name: '路人', min: 0 },
  { lv: 2, name: '龙套', min: 150 },
  { lv: 3, name: '配角', min: 400 },
  { lv: 4, name: '主角', min: 1000 },
  { lv: 5, name: '传说', min: 2000 }
]

export interface LevelInfo extends LevelDef {
  label: string
  next: LevelDef | null
}

const labelOf = (l: LevelDef) => `Lv.${l.lv} ${l.name}`

export function levelOf(xp: number): LevelInfo {
  let idx = 0
  LEVELS.forEach((l, i) => {
    if (xp >= l.min) idx = i
  })
  const cur = LEVELS[idx]
  return { ...cur, label: labelOf(cur), next: LEVELS[idx + 1] ?? null }
}

/** 首页等级条：当前经验 / 下一级门槛 */
export function xpBarPercent(xp: number): number {
  const { next } = levelOf(xp)
  if (!next) return 100
  return Math.min(100, (xp / next.min) * 100)
}

export interface GainResult {
  xpBefore: number
  xpAfter: number
  before: LevelInfo
  after: LevelInfo
  leveledUp: boolean
}

export function applyGain(xpBefore: number, gain: number): GainResult {
  const xpAfter = xpBefore + gain
  const before = levelOf(xpBefore)
  const after = levelOf(xpAfter)
  return { xpBefore, xpAfter, before, after, leveledUp: after.lv > before.lv }
}

export interface LevelProgressView {
  left: string
  right: string
  percent: number
  note: string
}

/** 通关结算页的等级进度块 */
export function levelProgressView(r: GainResult): LevelProgressView {
  const { xpAfter: xp, after } = r
  if (r.leveledUp) {
    const note = after.next
      ? `经验 ${xp} / ${after.min}，已升到${after.name}。下一级还差 ${after.next.min - xp} 经验。`
      : `经验 ${xp}，已升到${after.name}，这是最高等级。`
    return { left: r.before.label, right: after.label, percent: 100, note }
  }
  if (!after.next) {
    return { left: after.label, right: '', percent: 100, note: `经验 ${xp}，已是最高等级${after.name}。` }
  }
  return {
    left: after.label,
    right: labelOf(after.next),
    percent: Math.min(100, (xp / after.next.min) * 100),
    note: `经验 ${xp} / ${after.next.min}，再得 ${after.next.min - xp} 经验升到${after.next.name}。`
  }
}

export interface LevelSpan {
  label: string
  current: number
  total: number
  percent: number
}

/** “我的”页等级条：本级内进度（原型 Lv.3 配角 10 / 600）。最高级时 current 为累计经验、total 为 0 */
export function levelSpan(xp: number): LevelSpan {
  const lv = levelOf(xp)
  if (!lv.next) return { label: lv.label, current: xp, total: 0, percent: 100 }
  const total = lv.next.min - lv.min
  const current = xp - lv.min
  return { label: lv.label, current, total, percent: (current / total) * 100 }
}
