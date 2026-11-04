/** 通关结算：原型 01 第 14 屏。进入时把本话经验金币结算进个人资料（只一次） */

import { Text, View } from '@tarojs/components'
import Taro from '@tarojs/taro'
import { useEffect } from 'react'

import NavBar from '../../components/NavBar'
import { Btn, SafeBottom, StatChip } from '../../components/ui'
import { applyGain, levelProgressView } from '../../core/level'
import { sessionStats } from '../../core/session'
import { useStore } from '../../store'
import './index.scss'

export default function Clear() {
  const session = useStore((s) => s.session)

  useEffect(() => {
    const s = useStore.getState().session
    if (!s || !s.finished) {
      Taro.reLaunch({ url: '/pages/index/index' })
      return
    }
    useStore.getState().settleReward()
  }, [])

  if (!session || !session.finished || !session.reward) return <View className='screen clear' />

  const st = sessionStats(session)
  const gain = applyGain(session.reward.xpBefore, session.reward.xp)
  const lv = levelProgressView(gain)

  return (
    <View className='screen clear'>
      <View className='focus' />
      <NavBar />
      <View className='content clear-c'>
        <Text className='sfx big'>通关！</Text>
        <Text className='topic'>{session.quiz.title}</Text>
        <Text className='score-line'>
          答对 {st.correct} 格，共 {st.total} 格
        </Text>
        <View className='gains'>
          <StatChip icon='xp'>+{session.reward.xp}</StatChip>
          <StatChip icon='coin'>+{session.reward.coins}</StatChip>
        </View>
        <View className='lvup'>
          {gain.leveledUp && <Text className='sfx lv-sfx'>升级！</Text>}
          <View className='row'>
            <Text>{lv.left}</Text>
            <Text>{lv.right}</Text>
          </View>
          <View className='track'>
            <View className='track-i' style={{ width: `${lv.percent}%` }} />
          </View>
          <Text className='lv-note'>{lv.note}</Text>
        </View>
        <View className='clear-foot'>
          <Btn onClick={() => Taro.navigateTo({ url: '/pages/report/index' })}>查看复盘报告</Btn>
          <Btn kind='ghost' className='mt12' onClick={() => Taro.reLaunch({ url: '/pages/index/index' })}>
            回首页
          </Btn>
        </View>
      </View>
      <SafeBottom />
    </View>
  )
}
