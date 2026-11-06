/**
 * 学习数据：原型 03 第 2 屏。
 * 本周 / 本月 / 全部三档；两张卡片：学习时长（回答“学得勤不勤”）、题型正确率（回答“哪里容易错”），
 * 下面一句 AI 结论。统计秒回先画图，结论单独请求（数据没变时后端走缓存），没有就不显示。
 */

import { ScrollView, Text, View } from '@tarojs/components'
import Taro from '@tarojs/taro'
import { useEffect, useRef, useState } from 'react'

import Empty from '../../components/Empty'
import NavBar from '../../components/NavBar'
import { SafeBottom } from '../../components/ui'
import { TYPE_LABEL } from '../../core/format'
import { barHeights, compareText, isWeakType, RANGE_OPTIONS } from '../../core/stats'
import { getLearningStats, getStatsInsight } from '../../services/api'
import { ensureLogin } from '../../services/auth'
import type { LearningStats, StatsRange } from '../../types/api'
import './index.scss'

/** 结论的三种状态：加载中 / 有一句 / 没有（无数据、生成失败、请求失败都不显示） */
type InsightState = { status: 'loading' } | { status: 'done'; text: string | null }

const EMPTY_COPY: Record<StatsRange, string> = {
  week: '这周还没完结过一话。写一句想搞懂的事，3 分钟就能看完。',
  month: '这个月还没完结过一话。写一句想搞懂的事，3 分钟就能看完。',
  all: '完结第一话后，这里会画出你的学习时长和各题型正确率。'
}

export default function Stats() {
  const [range, setRange] = useState<StatsRange>('week')
  const [stats, setStats] = useState<LearningStats | null>(null)
  const [failed, setFailed] = useState(false)
  const [insight, setInsight] = useState<InsightState>({ status: 'loading' })
  /** 只采用最后一次请求的结果（快速切换时间段时，旧请求可能后返回） */
  const seq = useRef(0)

  const load = async (r: StatsRange) => {
    const mine = ++seq.current
    setFailed(false)
    setInsight({ status: 'loading' })
    try {
      if (!(await ensureLogin())) throw new Error('未登录')
      const data = await getLearningStats(r).promise
      if (mine !== seq.current) return
      setStats(data)
      if (data.question_count === 0) {
        setInsight({ status: 'done', text: null })
        return
      }
      try {
        const res = await getStatsInsight(r).promise
        if (mine === seq.current) setInsight({ status: 'done', text: res.insight })
      } catch (e) {
        console.warn('[stats] 结论加载失败', e)
        if (mine === seq.current) setInsight({ status: 'done', text: null })
      }
    } catch (e) {
      console.warn('[stats] 加载失败', e)
      if (mine === seq.current) setFailed(true)
    }
  }

  useEffect(() => {
    void load(range)
  }, [range])

  const shell = (body: JSX.Element) => (
    <View className='screen stats'>
      <NavBar variant='title' title='学习数据' left='back' />
      {body}
      <SafeBottom />
    </View>
  )

  const seg = (
    <View className='seg'>
      {RANGE_OPTIONS.map((o) => (
        <Text
          key={o.key}
          className={`seg-btn ${range === o.key ? 'is-on' : ''}`}
          onClick={() => o.key !== range && setRange(o.key)}
        >
          {o.label}
        </Text>
      ))}
    </View>
  )

  // 当前档的数据还没回来（首次进入或刚切换）
  const shown = stats && stats.range === range ? stats : null

  if (!shown) {
    return shell(
      <View className='content'>
        {seg}
        {failed ? (
          <Empty frame='数据' title='没连上服务' text='网络好像断了，检查一下再试。' action='重试' onAction={() => void load(range)} />
        ) : (
          <Text className='st-loading'>加载中…</Text>
        )}
      </View>
    )
  }

  if (shown.question_count === 0 && shown.total_minutes === 0) {
    return shell(
      <View className='content'>
        {seg}
        <Empty
          frame='第 0 话'
          title='还没有学习数据'
          text={EMPTY_COPY[range]}
          action='去闯关'
          onAction={() => Taro.switchTab({ url: '/pages/index/index' })}
        />
      </View>
    )
  }

  const heights = barHeights(shown.bars)
  const barsLabel = shown.bars.map((b) => `${b.label} ${b.minutes} 分钟`).join('，')

  return shell(
    <ScrollView scrollY className='scroll'>
      <View className='scroll-inner'>
        {seg}
        {failed && (
          <Text className='st-warn' onClick={() => void load(range)}>
            没连上服务，数据可能不是最新的，点这里重试。
          </Text>
        )}

        <View className='card st-card'>
          <View className='card-h'>
            <Text className='card-t'>学习时长</Text>
            <Text className='card-s'>{shown.period_label}</Text>
          </View>
          <View className='big-n'>
            <Text className='big-v'>{shown.total_minutes}</Text>
            <Text className='big-s'>{compareText(range, shown.total_minutes, shown.prev_minutes)}</Text>
          </View>
          <View className='bars' ariaLabel={barsLabel}>
            {shown.bars.map((b, i) => (
              <View key={b.label} className='bar-col'>
                <View
                  className={`bar ${b.is_current ? 'is-current' : ''} ${heights[i] === 0 ? 'is-zero' : ''}`}
                  style={{ height: `${heights[i]}%` }}
                />
              </View>
            ))}
          </View>
          <View className='bar-x'>
            {shown.bars.map((b) => (
              <Text key={b.label} className='bar-l'>
                {b.label}
              </Text>
            ))}
          </View>
        </View>

        <View className='card st-card'>
          <View className='card-h'>
            <Text className='card-t'>题型正确率</Text>
            <Text className='card-s'>
              {range === 'all' ? '全部' : range === 'week' ? '本周' : '本月'} {shown.question_count} 题
            </Text>
          </View>
          <View className='mtr'>
            {shown.type_accuracy.map((t) => (
              <View key={t.type} className={`mtr-row ${isWeakType(t) ? 'is-weak' : ''}`}>
                <Text className='mtr-n'>{TYPE_LABEL[t.type]}</Text>
                <View className='mtr-m'>
                  <View className='mtr-i' style={{ width: `${t.total ? t.accuracy : 0}%` }} />
                </View>
                <Text className='mtr-p'>{t.total ? `${t.accuracy}%` : '--'}</Text>
              </View>
            ))}
          </View>
          {insight.status === 'loading' && <Text className='insight is-loading'>AI 正在看你的数据…</Text>}
          {insight.status === 'done' && insight.text && <Text className='insight'>{insight.text}</Text>}
        </View>
        <View className='st-pad' />
      </View>
    </ScrollView>
  )
}
