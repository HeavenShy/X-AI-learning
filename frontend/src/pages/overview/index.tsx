/** 本话目录：原型 01 第 7 屏。题库生成后先给个全貌，数据来自接口的 title、summary 和 questions */

import { ScrollView, Text, View } from '@tarojs/components'
import Taro from '@tarojs/taro'
import { useEffect } from 'react'

import NavBar from '../../components/NavBar'
import { Btn, SafeBottom } from '../../components/ui'
import { DIFFICULTY_LABEL, estimateMinutes, TYPE_LABEL } from '../../core/format'
import { COINS_PER_CORRECT, XP_PER_CORRECT } from '../../core/level'
import { useStore } from '../../store'
import type { QuestionCount } from '../../types/api'
import './index.scss'

export default function Overview() {
  const quiz = useStore((s) => s.pendingQuiz)
  const req = useStore((s) => s.genRequest)

  useEffect(() => {
    if (!quiz) Taro.reLaunch({ url: '/pages/index/index' })
  }, [quiz])

  if (!quiz) return <View className='screen' />

  const count = quiz.questions.length as QuestionCount

  const onStart = () => {
    useStore.getState().startSession()
    Taro.redirectTo({ url: '/pages/quiz/index' })
  }

  const onReroll = () => {
    if (!req) return
    useStore.getState().requestGenerate({ ...req })
    Taro.redirectTo({ url: '/pages/generating/index' })
  }

  return (
    <View className='screen ov'>
      <NavBar variant='title' title='本话目录' left='back' />
      <ScrollView scrollY className='scroll'>
        <View className='scroll-inner'>
          <View className='ov-head'>
            <Text className='ov-title'>{quiz.title}</Text>
            <Text className='ov-sum'>{quiz.summary}</Text>
            <View className='meta'>
              <Text className='meta-i'>{count} 格</Text>
              <Text className='meta-i'>约 {estimateMinutes(count) ?? Math.ceil(count * 0.8)} 分钟</Text>
              <Text className='meta-i'>{DIFFICULTY_LABEL[req?.difficulty ?? 'mixed']}</Text>
            </View>
          </View>
          <View className='toc'>
            {quiz.questions.map((q, i) => (
              <View key={q.id} className='toc-li'>
                <Text className='n'>{i + 1}</Text>
                <Text className='t'>{TYPE_LABEL[q.type]}</Text>
                <Text className='kp'>{q.knowledge_point}</Text>
              </View>
            ))}
          </View>
          <Text className='ov-reward'>
            每答对一格 +{XP_PER_CORRECT} 经验、+{COINS_PER_CORRECT} 金币；答错不加，但会看到完整讲解。
          </Text>
          <View className='ov-foot'>
            <Btn onClick={onStart}>开始闯关</Btn>
            <Text className='link ov-link' onClick={onReroll}>
              换一批题
            </Text>
          </View>
        </View>
      </ScrollView>
      <SafeBottom />
    </View>
  )
}
