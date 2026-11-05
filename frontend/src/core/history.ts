/** 历史记录（原型 03 第 4 屏）：按日期分组、用时与时间格式 */

const pad = (n: number) => String(n).padStart(2, '0')

/** 后端时间是 ISO 8601 UTC（如 2026-11-05T02:03:04Z），iOS 也能直接解析 */
export const parseServerTime = (iso: string) => Date.parse(iso)

const startOfDay = (ts: number) => new Date(ts).setHours(0, 0, 0, 0)

export function dayLabel(ts: number, now: number): string {
  const diff = Math.round((startOfDay(now) - startOfDay(ts)) / 86_400_000)
  if (diff === 0) return '今天'
  if (diff === 1) return '昨天'
  const d = new Date(ts)
  const md = `${d.getMonth() + 1} 月 ${d.getDate()} 日`
  return d.getFullYear() === new Date(now).getFullYear() ? md : `${d.getFullYear()} 年 ${md}`
}

export interface DayGroup<T> {
  label: string
  items: T[]
}

/** 输入已按时间倒序；相邻同一天的归为一组 */
export function groupByDay<T>(items: T[], tsOf: (item: T) => number, now: number): DayGroup<T>[] {
  const groups: DayGroup<T>[] = []
  for (const item of items) {
    const label = dayLabel(tsOf(item), now)
    const last = groups[groups.length - 1]
    if (last && last.label === label) last.items.push(item)
    else groups.push({ label, items: [item] })
  }
  return groups
}

/** 原型：3 分 12 秒、4 分 05 秒；不足一分钟：40 秒 */
export function historyDuration(ms: number): string {
  const total = Math.round(ms / 1000)
  const m = Math.floor(total / 60)
  const s = total % 60
  return m > 0 ? `${m} 分 ${pad(s)} 秒` : `${s} 秒`
}

export function timeOfDay(ts: number): string {
  const d = new Date(ts)
  return `${pad(d.getHours())}:${pad(d.getMinutes())}`
}
