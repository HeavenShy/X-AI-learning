/**
 * 知识树：原型 03 第 3 屏。
 * 出题时 AI 给每一话归了大类主题；这里按主题列出已完结的话，按掌握度着色（≥80 绿、60–79 黄、<60 红）。
 * 点一话看当时的复盘报告；红色的话可以“再闯一轮”：用标题 + 答错的知识点直接出一组新题。
 */

import { ScrollView, Text, View } from '@tarojs/components'
import Taro from '@tarojs/taro'
import { useEffect, useState } from 'react'

import Empty from '../../components/Empty'
import NavBar from '../../components/NavBar'
import { SafeBottom } from '../../components/ui'
import { canRetry, masteryClass, retryInput } from '../../core/stats'
import { getKnowledgeTree } from '../../services/api'
import { ensureLogin } from '../../services/auth'
import { useStore } from '../../store'
import type { KnowledgeTree as Tree, TreeQuiz } from '../../types/api'
import './index.scss'

const RETRY_COUNT = 5

export default function KnowledgeTree() {
  const [tree, setTree] = useState<Tree | null>(null)
  const [failed, setFailed] = useState(false)

  const load = async () => {
    setFailed(false)
    try {
      if (!(await ensureLogin())) throw new Error('未登录')
      setTree(await getKnowledgeTree().promise)
    } catch (e) {
      console.warn('[knowledge-tree] 加载失败', e)
      setFailed(true)
    }
  }

  useEffect(() => {
    void load()
  }, [])

  const openReport = (q: TreeQuiz) =>
    Taro.navigateTo({ url: `/pages/report/index?quiz_id=${encodeURIComponent(q.quiz_id)}` })

  const retry = (q: TreeQuiz) => {
    const text = retryInput(q)
    const { setDraft, requestGenerate } = useStore.getState()
    // 同首页“开始闯关”：出题失败回到首页时输入框里还是这句
    setDraft({ text, count: RETRY_COUNT })
    requestGenerate({ text, count: RETRY_COUNT, difficulty: 'mixed' })
    Taro.navigateTo({ url: '/pages/generating/index' })
  }

  const shell = (body: JSX.Element) => (
    <View className='screen ktree'>
      <NavBar variant='title' title='知识树' left='back' />
      {body}
      <SafeBottom />
    </View>
  )

  if (!tree) {
    return shell(
      <View className='content'>
        {failed ? (
          <Empty frame='知识树' title='没连上服务' text='网络好像断了，检查一下再试。' action='重试' onAction={() => void load()} />
        ) : (
          <Text className='kt-loading'>加载中…</Text>
        )}
      </View>
    )
  }

  if (tree.topics.length === 0) {
    return shell(
      <View className='content'>
        <Empty
          frame='知识树'
          title='还没有知识树'
          text='每完结一话，AI 会把它挂到对应的主题下，学得越多树越大。'
          action='去闯关'
          onAction={() => Taro.switchTab({ url: '/pages/index/index' })}
        />
      </View>
    )
  }

  return shell(
    <ScrollView scrollY className='scroll'>
      <View className='scroll-inner'>
        <View className='legend'>
          <View className='lg'>
            <View className='lg-i g' />
            <Text>掌握 80% 以上</Text>
          </View>
          <View className='lg'>
            <View className='lg-i y' />
            <Text>60–79%</Text>
          </View>
          <View className='lg'>
            <View className='lg-i r' />
            <Text>低于 60%</Text>
          </View>
        </View>

        {tree.topics.map((t) => (
          <View key={t.topic} className='kt-topic'>
            <View className='node'>
              <View className='node-t'>
                <Text className='node-b'>{t.topic}</Text>
                <Text className='node-s'>{t.quiz_count} 话</Text>
              </View>
              <Text className={`pc ${masteryClass(t.accuracy)}`}>{t.accuracy}%</Text>
            </View>
            <View className='kt-kids'>
              {t.quizzes.map((q, i) => (
                <View key={q.quiz_id} className='kt-kid'>
                  <View className={`kt-v ${i === t.quizzes.length - 1 ? 'is-last' : ''}`} />
                  <View className='kt-h' />
                  <View className='node is-kid' hoverClass='node-pressed' onClick={() => openReport(q)}>
                    <Text className='node-n'>{q.title}</Text>
                    {canRetry(q) && (
                      <Text
                        className='retry'
                        onClick={(e) => {
                          e.stopPropagation()
                          retry(q)
                        }}
                      >
                        再闯一轮
                      </Text>
                    )}
                    <Text className={`pc ${masteryClass(q.accuracy)}`}>{q.accuracy}%</Text>
                  </View>
                </View>
              ))}
            </View>
          </View>
        ))}
        <Text className='kt-tip'>点一话看当时的复盘；红色的可以直接再闯一轮，专练答错的知识点。</Text>
        <View className='kt-pad' />
      </View>
    </ScrollView>
  )
}
