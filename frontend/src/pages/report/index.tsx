/**
 * 复盘报告：原型 01 第 15（生成中）、16（完成）屏。
 * 分数在本地算好立刻显示；三句总结、掌握度、下话预告等报告接口返回后填入。
 */

import { ScrollView, Text, View } from '@tarojs/components'
import Taro from '@tarojs/taro'
import { useEffect } from 'react'

import NavBar from '../../components/NavBar'
import { Btn, SafeBottom } from '../../components/ui'
import { formatDuration } from '../../core/format'
import { WEAK_BELOW } from '../../core/mastery'
import { sessionStats, toAnswerRecords } from '../../core/session'
import { generateReport } from '../../services/api'
import { useStore } from '../../store'
import type { QuestionCount } from '../../types/api'
import './index.scss'

const NUMS = ['一', '二', '三']

function Placeholder({ short = false }: { short?: boolean }) {
  return <View className={`ph ${short ? 's' : ''}`} />
}

export default function ReportPage() {
  const session = useStore((s) => s.session)
  const report = useStore((s) => s.report)

  const load = () => {
    const s = useStore.getState().session
    if (!s) return
    useStore.getState().setReport({ quizId: s.quiz.quiz_id, status: 'loading', data: null })
    const p = generateReport({
      quiz_id: s.quiz.quiz_id,
      topic: s.quiz.title,
      questions: s.quiz.questions,
      answer_records: toAnswerRecords(s)
    })
    p.promise
      .then((data) => useStore.getState().setReport({ quizId: s.quiz.quiz_id, status: 'done', data }))
      .catch(() => useStore.getState().setReport({ quizId: s.quiz.quiz_id, status: 'error', data: null }))
  }

  useEffect(() => {
    const { session: s, report: r } = useStore.getState()
    if (!s || !s.finished) {
      Taro.reLaunch({ url: '/pages/index/index' })
      return
    }
    if (!r || r.quizId !== s.quiz.quiz_id || r.status === 'error') load()
  }, [])

  if (!session || !session.finished) return <View className='screen' />

  const st = sessionStats(session)
  const reward = session.reward
  const current = report && report.quizId === session.quiz.quiz_id ? report : null
  const data = current?.status === 'done' ? current.data : null

  const onAgain = () => {
    useStore.getState().requestGenerate({
      text: session.quiz.user_input,
      count: session.quiz.questions.length as QuestionCount,
      difficulty: session.difficulty
    })
    Taro.reLaunch({ url: '/pages/generating/index' })
  }

  return (
    <View className='screen report'>
      <NavBar variant='title' title='本话完结' left='back' />
      <ScrollView scrollY className='scroll'>
        <View className='scroll-inner'>
          <View className='page'>
            <View className='pn wide score-pn'>
              <Text className='num'>
                {st.accuracy}
                <Text className='num-s'>分</Text>
              </Text>
              <View className='t'>
                <Text className='t-b'>{session.quiz.title}</Text>
                <Text>
                  答对 {st.correct} 题，共 {st.total} 题，用时 {formatDuration(st.durationMs)}
                </Text>
                {reward && (
                  <Text>
                    获得 {reward.xp} 经验、{reward.coins} 金币
                  </Text>
                )}
              </View>
            </View>

            {!data && (
              <View className='pn wide'>
                {current?.status === 'error' ? (
                  <View className='fail-note'>
                    <Text className='fail-t'>复盘没写出来，可能是网络不稳。</Text>
                    <View className='retry' hoverClass='retry-pressed' onClick={load}>
                      重试
                    </View>
                  </View>
                ) : (
                  <View className='wait-note'>
                    <View className='dots'>
                      <View className='dot' />
                      <View className='dot' />
                      <View className='dot' />
                    </View>
                    <Text>AI 正在根据你的答题情况写复盘，约 10 秒</Text>
                  </View>
                )}
              </View>
            )}
            {data && (
              <View className='pn wide pn-h'>
                <Text className='h5'>三格记住它</Text>
              </View>
            )}

            <View className='strips'>
              {NUMS.map((n, i) => (
                <View key={n} className='pn strip'>
                  <Text className='em'>{n}</Text>
                  {data ? (
                    <Text>{data.three_line_summary[i]}</Text>
                  ) : (
                    <>
                      <Placeholder />
                      <Placeholder />
                      <Placeholder short />
                    </>
                  )}
                </View>
              ))}
            </View>

            <View className='pn wide'>
              <Text className='h5'>掌握度</Text>
              {data ? (
                <View className='kps'>
                  {data.knowledge_mastery.map((m) => (
                    <View key={m.point} className={`kp-li ${m.accuracy < WEAK_BELOW ? 'weak' : ''}`}>
                      <Text className='kp-name'>{m.point}</Text>
                      <View className='meter'>
                        <View className='meter-i' style={{ width: `${m.accuracy}%` }} />
                      </View>
                      <Text className='pct'>{m.accuracy}%</Text>
                    </View>
                  ))}
                </View>
              ) : (
                <>
                  <Placeholder />
                  <Placeholder />
                  <Placeholder short />
                </>
              )}
            </View>

            <View className='pn wide'>
              <Text className='h5'>下话预告</Text>
              {data ? (
                <View className='next'>
                  {data.advice.map((a) => (
                    <Text key={a} className='next-li'>
                      {a}
                    </Text>
                  ))}
                </View>
              ) : (
                <>
                  <Placeholder />
                  <Placeholder short />
                </>
              )}
            </View>
          </View>
          <View className='report-pad' />
        </View>
      </ScrollView>
      <View className='report-actions'>
        <Btn className='ra-primary' disabled={!data} onClick={() => Taro.navigateTo({ url: '/pages/poster/index' })}>
          生成分享海报
        </Btn>
        <Btn kind='ghost' className='ra-ghost' onClick={onAgain}>
          再闯一轮
        </Btn>
      </View>
      <SafeBottom />
    </View>
  )
}
