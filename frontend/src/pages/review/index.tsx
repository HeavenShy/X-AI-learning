/**
 * 复习（底部第二个标签，原型 03 第 7、8 屏 pages/review）：错题本。
 * 按话分组列出还没掌握的错题（题型、题干、错几次），点开去重做；答对一次就移出错题本。
 * 标签页不会重新挂载：每次切到这里（含从重做页返回）都重新拉列表。
 * 遗忘曲线排期、宝藏关、已掌握列表不在本期范围。
 */

import { ScrollView, Text, View } from '@tarojs/components'
import Taro, { useDidShow } from '@tarojs/taro'
import { useRef, useState } from 'react'

import Empty from '../../components/Empty'
import NavBar from '../../components/NavBar'
import { TabBarSpace, useTabSelected } from '../../components/TabPage'
import { TYPE_LABEL } from '../../core/format'
import { groupMistakes, withoutMistake, wrongCountLabel } from '../../core/review'
import { TAB_INDEX } from '../../core/tabs'
import { listMistakes } from '../../services/api'
import { ensureLogin } from '../../services/auth'
import { useStore } from '../../store'
import type { MistakeItem } from '../../types/api'
import './index.scss'

export default function Review() {
  useTabSelected(TAB_INDEX.review)
  const setReviewing = useStore((s) => s.setReviewing)
  const [items, setItems] = useState<MistakeItem[] | null>(null)
  const [failed, setFailed] = useState(false)
  /** 只采用最后一次请求的结果（快速来回切标签时，旧请求可能后返回） */
  const seq = useRef(0)

  const load = async () => {
    const mine = ++seq.current
    setFailed(false)
    try {
      if (!(await ensureLogin())) throw new Error('未登录')
      const data = await listMistakes().promise
      if (mine === seq.current) setItems(data.items)
    } catch (e) {
      console.warn('[review] 加载失败', e)
      if (mine === seq.current) setFailed(true)
    }
  }

  useDidShow(() => {
    // 重做页刚答对的那道：先在本地去掉，免得重新拉到之前闪一下
    const { reviewMastered, setReviewMastered } = useStore.getState()
    if (reviewMastered) {
      setItems((cur) => (cur ? withoutMistake(cur, reviewMastered) : cur))
      setReviewMastered(null)
    }
    void load()
  })

  const open = (item: MistakeItem) => {
    setReviewing(item)
    Taro.navigateTo({ url: '/pages/review-answer/index' })
  }

  const shell = (body: JSX.Element) => (
    <View className='screen review'>
      <NavBar variant='brand' title='复习' />
      {body}
      <TabBarSpace />
    </View>
  )

  if (!items) {
    if (!failed) {
      return shell(
        <View className='content'>
          <Text className='rv-loading'>加载中…</Text>
        </View>
      )
    }
    return shell(
      <View className='content'>
        <Empty frame='复习' title='没连上服务' text='网络好像断了，检查一下再试。' action='重试' onAction={() => void load()} />
      </View>
    )
  }

  if (items.length === 0) {
    return shell(
      <View className='content'>
        <Empty
          frame='复习'
          title='还没有错题'
          text='闯关答错的题会回到这里，重做答对就算掌握。'
          action='去闯关'
          onAction={() => Taro.switchTab({ url: '/pages/index/index' })}
        />
      </View>
    )
  }

  const groups = groupMistakes(items)
  return shell(
    <ScrollView scrollY className='scroll'>
      <View className='scroll-inner'>
        <View className='rv-head'>
          <Text className='rv-title'>错题本</Text>
          <Text className='rv-count'>{items.length} 道还没掌握</Text>
        </View>
        <Text className='rv-tip'>点开重做，答对一次就移出错题本。</Text>
        {failed && (
          <Text className='rv-tip is-warn' onClick={() => void load()}>
            没连上服务，列表可能不是最新的，点这里重试。
          </Text>
        )}
        {groups.map((g) => (
          <View key={g.quizId}>
            <View className='topic-h'>
              <Text className='topic-t'>{g.title}</Text>
              <Text className='topic-n'>{g.count} 道</Text>
            </View>
            <View className='list'>
              {g.items.map((m) => (
                <View key={m.question.id} className='li wq' hoverClass='li-pressed' onClick={() => open(m)}>
                  <Text className='q'>{m.question.stem}</Text>
                  <View className='meta'>
                    <Text className='pill'>{TYPE_LABEL[m.question.type]}</Text>
                    <Text>{wrongCountLabel(m.wrong_count)}</Text>
                  </View>
                </View>
              ))}
            </View>
          </View>
        ))}
        <View className='rv-pad' />
      </View>
    </ScrollView>
  )
}
