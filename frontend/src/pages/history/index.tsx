/**
 * 历史记录：原型 03 第 4 屏（列表）、第 6 屏（空状态）。
 * - 已完结的话来自后端（分页加载，滚到底加载下一页）；点开看当时的复盘报告。
 * - “没答完”只有本机那一条可续答的会话（服务器不知道答到第几格），点“继续”接着答。
 * 按日期分组，分数低于 60 用红色。
 */

import { ScrollView, Text, View } from '@tarojs/components'
import Taro from '@tarojs/taro'
import { useEffect, useState } from 'react'

import Empty from '../../components/Empty'
import NavBar from '../../components/NavBar'
import { SafeBottom } from '../../components/ui'
import { groupByDay, historyDuration, parseServerTime, timeOfDay } from '../../core/history'
import { WEAK_BELOW } from '../../core/mastery'
import { listQuizzes } from '../../services/api'
import { ensureLogin } from '../../services/auth'
import { useStore } from '../../store'
import type { HistoryItem } from '../../types/api'
import './index.scss'

const PAGE_SIZE = 20

type Filter = 'all' | 'unfinished' | 'finished'

type Row =
  | { kind: 'finished'; ts: number; item: HistoryItem }
  | { kind: 'unfinished'; ts: number; title: string; cell: number }

interface Loaded {
  items: HistoryItem[]
  total: number
  page: number
}

export default function History() {
  const session = useStore((s) => s.session)
  const [loaded, setLoaded] = useState<Loaded | null>(null)
  const [failed, setFailed] = useState(false)
  const [loadingMore, setLoadingMore] = useState(false)
  const [filter, setFilter] = useState<Filter>('all')

  const loadFirst = async () => {
    setFailed(false)
    try {
      if (!(await ensureLogin())) throw new Error('未登录')
      const p = await listQuizzes(1, PAGE_SIZE).promise
      setLoaded({ items: p.items, total: p.total, page: 1 })
    } catch (e) {
      console.warn('[history] 加载失败', e)
      setFailed(true)
    }
  }

  const loadMore = async () => {
    if (!loaded || loadingMore || loaded.items.length >= loaded.total) return
    setLoadingMore(true)
    try {
      const p = await listQuizzes(loaded.page + 1, PAGE_SIZE).promise
      setLoaded({ items: [...loaded.items, ...p.items], total: p.total, page: loaded.page + 1 })
    } catch {
      Taro.showToast({ title: '没加载出来，稍后再试', icon: 'none' })
    } finally {
      setLoadingMore(false)
    }
  }

  useEffect(() => {
    void loadFirst()
  }, [])

  const unfinished: Row[] =
    session && !session.finished
      ? [{ kind: 'unfinished', ts: session.updatedAt, title: session.quiz.title, cell: session.index + 1 }]
      : []
  const finished: Row[] = (loaded?.items ?? []).map((item) => ({
    kind: 'finished',
    ts: parseServerTime(item.created_at),
    item
  }))
  const finishedTotal = loaded?.total ?? 0

  const pageShell = (body: JSX.Element) => (
    <View className='screen history'>
      <NavBar variant='title' title='历史记录' left='back' />
      {body}
      <SafeBottom />
    </View>
  )

  // 首次加载中：只留导航栏，避免空状态一闪而过
  if (!loaded && !failed) return pageShell(<View className='content' />)

  if (unfinished.length === 0 && finishedTotal === 0) {
    return pageShell(
      <View className='content'>
        {failed ? (
          <Empty
            frame='第 0 话'
            title='没连上服务'
            text='网络好像断了，检查一下再试。'
            action='重试'
            onAction={() => void loadFirst()}
          />
        ) : (
          <Empty
            frame='第 0 话'
            title='还没有学习记录'
            text='写一句想搞懂的事，3 分钟就能看完第一话。'
            action='去出第一话'
            onAction={() => Taro.switchTab({ url: '/pages/index/index' })}
          />
        )}
      </View>
    )
  }

  const rows = (filter === 'unfinished' ? unfinished : filter === 'finished' ? finished : [...unfinished, ...finished])
    .slice()
    .sort((a, b) => b.ts - a.ts)
  const groups = groupByDay(rows, (r) => r.ts, Date.now())
  const tabs: { key: Filter; label: string }[] = [
    { key: 'all', label: `全部 ${unfinished.length + finishedTotal}` },
    { key: 'unfinished', label: `没答完 ${unfinished.length}` },
    { key: 'finished', label: `已完结 ${finishedTotal}` }
  ]

  const openReport = (quizId: string) =>
    Taro.navigateTo({ url: `/pages/report/index?quiz_id=${encodeURIComponent(quizId)}` })

  return pageShell(
    <ScrollView scrollY className='scroll' lowerThreshold={120} onScrollToLower={() => void loadMore()}>
      <View className='scroll-inner'>
        <View className='tabs'>
          {tabs.map((t) => (
            <Text key={t.key} className={`tab-btn ${filter === t.key ? 'is-on' : ''}`} onClick={() => setFilter(t.key)}>
              {t.label}
            </Text>
          ))}
        </View>
        {failed && <Text className='hist-tip'>已完结的记录没加载出来，返回后再进来试试。</Text>}
        {groups.map((g, gi) => (
          <View key={g.label}>
            <Text className={`day ${gi === 0 ? 'is-first' : ''}`}>{g.label}</Text>
            <View className='list hist'>
              {g.items.map((r) =>
                r.kind === 'finished' ? (
                  <View
                    key={r.item.quiz_id}
                    className='li'
                    hoverClass='li-pressed'
                    onClick={() => openReport(r.item.quiz_id)}
                  >
                    <View className='grow'>
                      <Text>{r.item.title}</Text>
                      <Text className='small'>
                        {r.item.question_count} 题，{historyDuration(r.item.total_duration_ms)}
                      </Text>
                    </View>
                    <Text className={`sc ${r.item.accuracy < WEAK_BELOW ? 'r' : ''}`}>{r.item.accuracy}</Text>
                  </View>
                ) : (
                  <View
                    key='unfinished'
                    className='li'
                    hoverClass='li-pressed'
                    onClick={() => Taro.navigateTo({ url: '/pages/quiz/index' })}
                  >
                    <View className='grow'>
                      <Text>{r.title}</Text>
                      <Text className='small'>
                        答到第 {r.cell} 格，{timeOfDay(r.ts)} 中断
                      </Text>
                    </View>
                    <Text className='go'>继续</Text>
                  </View>
                )
              )}
            </View>
          </View>
        ))}
        {loadingMore && <Text className='hist-tip'>加载中…</Text>}
        <View className='hist-pad' />
      </View>
    </ScrollView>
  )
}
