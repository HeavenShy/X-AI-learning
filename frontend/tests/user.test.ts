import { test } from 'node:test'
import assert from 'node:assert/strict'

import { dayLabel, groupByDay, historyDuration, parseServerTime, timeOfDay } from '../src/core/history'
import { levelSpan } from '../src/core/level'
import { avatarChar, NICKNAME_MAX, validateNickname } from '../src/core/nickname'
import { withReauth } from '../src/core/reauth'

// ---------- 我的：等级内进度（原型：Lv.3 配角，10 / 600） ----------

test('等级内进度：410 经验 = 配角 10 / 600', () => {
  assert.deepEqual(levelSpan(410), { label: 'Lv.3 配角', current: 10, total: 600, percent: (10 / 600) * 100 })
})

test('等级内进度：刚好升级时从 0 开始', () => {
  assert.deepEqual(levelSpan(150), { label: 'Lv.2 龙套', current: 0, total: 250, percent: 0 })
  assert.equal(levelSpan(0).total, 150)
})

test('等级内进度：最高级显示累计经验，进度满', () => {
  assert.deepEqual(levelSpan(2300), { label: 'Lv.5 传说', current: 2300, total: 0, percent: 100 })
})

// ---------- 历史记录：按日期分组（原型：今天 / 昨天 / 11 月 1 日） ----------

// 用本地时间构造，测试与运行环境时区无关（月份从 0 开始）
const at = (m: number, d: number, h: number, min = 0, y = 2026) => new Date(y, m - 1, d, h, min).getTime()
const NOW = at(11, 5, 21)

test('日期标签', () => {
  assert.equal(dayLabel(at(11, 5, 0, 10), NOW), '今天')
  assert.equal(dayLabel(at(11, 4, 23, 10), NOW), '昨天')
  assert.equal(dayLabel(at(11, 1, 8), NOW), '11 月 1 日')
  assert.equal(dayLabel(at(12, 31, 8, 0, 2025), NOW), '2025 年 12 月 31 日')
})

test('按日期分组，保持原有顺序（新的在前）', () => {
  const items = [
    { id: 'a', ts: at(11, 5, 10) },
    { id: 'b', ts: at(11, 4, 23, 10) },
    { id: 'c', ts: at(11, 4, 9) },
    { id: 'd', ts: at(11, 1, 9) }
  ]
  const groups = groupByDay(items, (i) => i.ts, NOW)
  assert.deepEqual(
    groups.map((g) => [g.label, g.items.map((i) => i.id)]),
    [
      ['今天', ['a']],
      ['昨天', ['b', 'c']],
      ['11 月 1 日', ['d']]
    ]
  )
})

test('解析后端时间：ISO 8601 UTC（带 Z）', () => {
  assert.equal(parseServerTime('2026-11-04T15:30:00Z'), Date.UTC(2026, 10, 4, 15, 30, 0))
  assert.ok(Number.isNaN(parseServerTime('garbage')))
})

test('历史记录用时（原型：3 分 12 秒、4 分 05 秒、1 分 40 秒）', () => {
  assert.equal(historyDuration(192_000), '3 分 12 秒')
  assert.equal(historyDuration(245_000), '4 分 05 秒')
  assert.equal(historyDuration(100_000), '1 分 40 秒')
  assert.equal(historyDuration(40_400), '40 秒')
})

test('中断时间只显示时分（原型：23:10 中断）', () => {
  assert.equal(timeOfDay(new Date(2026, 10, 4, 23, 10).getTime()), '23:10')
  assert.equal(timeOfDay(new Date(2026, 10, 4, 8, 5).getTime()), '08:05')
})

// ---------- 昵称 ----------

test('头像显示昵称首字（原型：林）', () => {
  assert.equal(avatarChar('林小满'), '林')
  assert.equal(avatarChar('🐟鱼皮'), '🐟')
  assert.equal(avatarChar('  '), '学')
  assert.equal(avatarChar(''), '学')
})

test('昵称校验：不能为空、最多 20 个字', () => {
  assert.equal(validateNickname('   '), '昵称不能为空')
  assert.equal(validateNickname('鱼'.repeat(NICKNAME_MAX)), null)
  assert.equal(validateNickname('鱼'.repeat(NICKNAME_MAX - 1) + '🐟'), null)
  assert.equal(validateNickname('鱼'.repeat(NICKNAME_MAX + 1)), `昵称最多 ${NICKNAME_MAX} 个字`)
})

// ---------- 登录过期：重新登录一次再重发 ----------

class ApiErr extends Error {
  constructor(public code: number) {
    super(String(code))
  }
}

test('token 过期（4010）时重新登录并重发一次', async () => {
  const tokens: (string | null)[] = []
  let current: string | null = 'old'
  const result = await withReauth(
    (token) => {
      tokens.push(token)
      return token === 'old' ? Promise.reject(new ApiErr(4010)) : Promise.resolve('ok')
    },
    {
      getToken: () => current,
      relogin: async () => {
        current = 'new'
        return current
      },
      isUnauthorized: (e) => e instanceof ApiErr && e.code === 4010
    }
  )
  assert.equal(result, 'ok')
  assert.deepEqual(tokens, ['old', 'new'])
})

test('重新登录后仍然 4010 就放弃，不无限重试', async () => {
  let relogins = 0
  await assert.rejects(
    withReauth(() => Promise.reject(new ApiErr(4010)), {
      getToken: () => 't',
      relogin: async () => {
        relogins++
        return 't2'
      },
      isUnauthorized: (e) => e instanceof ApiErr && e.code === 4010
    }),
    (e: any) => e.code === 4010
  )
  assert.equal(relogins, 1)
})

test('其他错误直接抛出，不重新登录', async () => {
  let relogins = 0
  await assert.rejects(
    withReauth(() => Promise.reject(new ApiErr(4004)), {
      getToken: () => 't',
      relogin: async () => {
        relogins++
        return 't2'
      },
      isUnauthorized: (e) => e instanceof ApiErr && e.code === 4010
    })
  )
  assert.equal(relogins, 0)
})

test('重新登录失败（如网络断了）时抛出原来的 4010', async () => {
  await assert.rejects(
    withReauth(() => Promise.reject(new ApiErr(4010)), {
      getToken: () => 't',
      relogin: async () => null,
      isUnauthorized: (e) => e instanceof ApiErr && e.code === 4010
    }),
    (e: any) => e.code === 4010
  )
})
